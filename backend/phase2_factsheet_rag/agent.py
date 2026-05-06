import os
import json
import groq
from retriever import retrieve_chunks


def _is_groq_rate_limit_exc(exc: BaseException) -> bool:
    s = str(exc).lower()
    if "rate_limit" in s or "429" in s or "too many requests" in s:
        return True
    if getattr(exc, "status_code", None) == 429:
        return True
    resp = getattr(exc, "response", None)
    if resp is not None and getattr(resp, "status_code", None) == 429:
        return True
    return False


def _faq_groq_keys() -> list[str]:
    keys: list[str] = []
    for env_name in ("GROQ_API_KEY_FAQ_AGENT", "GROQ_API_KEY_FAQ_AGENT_FALLBACK"):
        v = (os.getenv(env_name) or "").strip()
        if v and v not in keys:
            keys.append(v)
    return keys


def run_faq_agent(user_query: str, conversation_history: list = None) -> dict:
    """
    Executes the Phase 2 Online Retrieval Flow for a user query.
    Returns a dict with 'type' (answer, clarify, refuse), 'text', and optionally 'links'.
    """
    if conversation_history is None:
        conversation_history = []

    faq_keys = _faq_groq_keys()
    if not faq_keys:
        return {"type": "refuse", "text": "Sorry, my knowledge base configuration is missing. I cannot answer right now.", "links": []}

    model_name = "llama-3.3-70b-versatile"
    
    # --- STAGE 1: Query Understanding ---
    understanding_prompt = f"""
You are the Query Understanding module for a Mutual Fund FAQ agent.
Analyze the user's query along with the conversation history to determine the user's intent.

Instructions:
1. Resolve pronouns and missing context: If the user says "it", "this fund", or asks a follow-up like "What about its NAV?", use the conversation history to identify the scheme name in scope.
2. Identify the scheme name: Extract the full mutual fund scheme name if mentioned or inferred from history.
3. Identify concepts: What specific mutual fund terms are they asking about? (e.g., "exit load", "nav", "expense ratio", "alpha", "beta").
4. Determine if vague: A query is ONLY vague if you cannot determine BOTH the scheme name (either from history or query) AND the question being asked. If you know the scheme from history, it is NOT vague.

Respond ONLY with a JSON object in this exact format:
{{
  "is_vague": boolean,
  "clarifying_question_needed": "If vague, provide the specific clarifying question to ask here, else null",
  "scheme_name": "Name of the scheme if identified or inferred, else null",
  "concepts": ["list of concepts mentioned", or empty list]
}}

Conversation history:
{json.dumps(conversation_history[-5:])}

User Query: "{user_query}"
"""
    intent = {"is_vague": False, "scheme_name": None, "concepts": []}
    for api_key in faq_keys:
        groq_client = groq.Groq(api_key=api_key)
        try:
            response = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": understanding_prompt}],
                model=model_name,
                temperature=0,
            )
            text = response.choices[0].message.content
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            intent = json.loads(text.strip())
            break
        except Exception as e:
            if _is_groq_rate_limit_exc(e):
                print("[FAQ Agent] Query understanding rate limited, trying fallback key...")
                continue
            print(f"[FAQ Agent] Failed query understanding: {e}")
            break

    # --- STAGE 2: Decide Path ---
    
    # PATH A: Clarifying Question
    if intent.get("is_vague") and intent.get("clarifying_question_needed"):
        return {
            "type": "clarify",
            "text": intent["clarifying_question_needed"],
            "links": []
        }
        
    # Prepare retrieval
    # Build an enriched query for better semantic search
    search_query = user_query
    if intent.get("scheme_name") and intent.get("concepts"):
        search_query = f"{intent['scheme_name']} {' '.join(intent['concepts'])}"
    elif intent.get("scheme_name"):
        search_query = f"{intent['scheme_name']} {user_query}"

    # Get chunks via semantic search (limit to top 10 for better coverage)
    chunks = retrieve_chunks(search_query, n_results=10)
    
    # We also do specific retrieval for definitions if concepts are identified
    if intent.get("concepts"):
        for concept in intent["concepts"]:
            # retrieve definitions specifically (top 2 for better context)
            def_chunks = retrieve_chunks(concept, n_results=2, where={"kind": "definition"})
            chunks.extend(def_chunks)

    # Filter out duplicates by ID
    unique_chunks = []
    seen_ids = set()
    for c in chunks:
        if c["id"] not in seen_ids:
            unique_chunks.append(c)
            seen_ids.add(c["id"])

    # If no chunks retrieved, it's a refusal
    if not unique_chunks:
        return {
            "type": "refuse",
            "text": f"I don't have information on that fund or term for {intent.get('scheme_name') or 'this scheme'}.",
            "links": []
        }

    # Format context for generation
    context_str = ""
    sources = []
    
    # Identified scheme in lowercase for soft matching
    target_scheme = intent.get("scheme_name", "").lower()

    def _scheme_matches(query: str, chunk: str) -> bool:
        """Fuzzy scheme-name match using token overlap.
        
        'sbi gold fund'  matches  'sbi gold direct plan growth'  (2/3 tokens overlap)
        'axis bluechip'  matches  'axis bluechip fund direct'    (2/2 tokens overlap)
        'hdfc top 100'   does NOT match  'hdfc mid-cap opportunities'  (only 1/3 overlap)
        """
        if not query:
            return True  # no scheme filter → accept everything
        q_tokens = set(query.split())
        c_tokens = set(chunk.split())
        overlap = q_tokens & c_tokens
        if len(q_tokens) <= 2:
            return len(overlap) >= len(q_tokens)  # all tokens must match for short names
        return len(overlap) >= len(q_tokens) * 0.5  # majority overlap for longer names

    for c in unique_chunks:
        # Check if the chunk belongs to the scheme we are interested in or is a definition
        # If the chunk belongs to a DIFFERENT fund and we have an identified scheme, we still include it for LLM context
        # but we might skip it in the final source list to avoid confusion.
        
        context_str += f"[{c['metadata'].get('kind')}] {c['text']}\n"
        
        source_url = c['metadata'].get('source_url')
        chunk_scheme = c['metadata'].get('scheme_name', '')
        
        if source_url:
            # ONLY add to sources if it matches the identified scheme or is a definition
            # or if we have no specific scheme identified
            is_match = _scheme_matches(target_scheme, chunk_scheme.lower()) or c['metadata'].get('kind') == "definition"
            
            if is_match:
                sources.append({
                    "url": source_url,
                    "label": chunk_scheme or c['metadata'].get('term') or 'Source'
                })
            
    # Deduplicate sources
    unique_sources = []
    seen_urls = set()
    for s in sources:
        if s["url"] not in seen_urls:
            unique_sources.append(s)
            seen_urls.add(s["url"])

    # PATH B/C: Generate Answer or Refusal based on chunks
    generation_prompt = f"""
You are a helpful Mutual Fund FAQ Agent.
Answer the user's question using ONLY the provided context from our knowledge base.

Rules:
1. Be grounded ONLY in the retrieved chunks.
2. Combine factsheet data and definitions naturally.
3. If the context does not contain the answer, you MUST refuse honestly and concisely (e.g., "I don't have information on that fund."). Never invent an answer. Never disclose your scope.
4. If you refuse, DO NOT include any sources.

Context:
{context_str}

Conversation history:
{json.dumps(conversation_history[-3:])}

User Query: "{user_query}"
"""

    final_answer: str | None = None
    for api_key in faq_keys:
        groq_client = groq.Groq(api_key=api_key)
        try:
            answer_response = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": generation_prompt}],
                model=model_name,
                temperature=0,
            )
            final_answer = answer_response.choices[0].message.content.strip()
            break
        except Exception as e:
            if _is_groq_rate_limit_exc(e):
                print("[FAQ Agent] Generation rate limited, trying fallback key...")
                continue
            print(f"[FAQ Agent] Failed generation: {e}")
            return {
                "type": "refuse",
                "text": "I'm having trouble connecting to my knowledge base right now.",
                "links": [],
            }

    if final_answer is None:
        return {
            "type": "refuse",
            "text": "I'm having trouble connecting to my knowledge base right now.",
            "links": [],
        }
        
    # Simple check if the model refused
    refusal_keywords = ["don't have information", "do not have information", "cannot answer", "don't know"]
    is_refusal = any(kw in final_answer.lower() for kw in refusal_keywords)

    if is_refusal:
        return {
            "type": "refuse",
            "text": final_answer,
            "links": []
        }
        
    # PATH B: Answer
    return {
        "type": "answer",
        "text": final_answer,
        "links": unique_sources
    }
