import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { MessageSquare, X, Send, Bot, ExternalLink, RefreshCw, Mic, Sparkles, Mail, Check } from 'lucide-react';
import VoicePanel from './VoicePanel';
import TypewriterMessage from './TypewriterMessage';
import './Chatbot.css';

const API_BASE = import.meta.env.DEV
  ? ''
  : (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8002').replace(/\/$/, '');
const API_URL = `${API_BASE}/api/chat`;
const SEND_DETAILS_URL = `${API_BASE}/api/send-booking-details`;

function newSessionId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `sess-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

const Chatbot = ({ isDark = true }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([
    {
      id: 1,
      role: 'assistant',
      content: 'Hi, how can I help you?',
      links: []
    }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState(() => newSessionId());
  const [uiMode, setUiMode] = useState('chat');
  const [chatClosed, setChatClosed] = useState(false);
  const [bookingCode, setBookingCode] = useState(null);
  // Email form state for "Send me the booking details"
  const [showEmailForm, setShowEmailForm] = useState(null); // message id
  const [emailInput, setEmailInput] = useState('');
  const [emailSending, setEmailSending] = useState(false);
  const [emailSent, setEmailSent] = useState({}); // { messageId: true }
  /** After switching to Voice, wait for first assistant (welcome) typewriter to finish before opening the voice WebSocket. */
  const [voiceConnectReady, setVoiceConnectReady] = useState(false);
  const messagesEndRef = useRef(null);

  const firstAssistantId = useMemo(() => {
    const m = messages.find((x) => x.role === 'assistant');
    return m?.id ?? null;
  }, [messages]);

  const handleVoiceIntroAnimationDone = useCallback(() => {
    setVoiceConnectReady(true);
  }, []);

  useEffect(() => {
    if (uiMode !== 'voice') {
      setVoiceConnectReady(false);
    }
  }, [uiMode]);

  useEffect(() => {
    if (uiMode !== 'voice' || voiceConnectReady) return;
    if (!messages.some((m) => m.role === 'assistant')) {
      setVoiceConnectReady(true);
    }
  }, [uiMode, messages, voiceConnectReady]);

  useEffect(() => {
    if (uiMode !== 'chat') return;
    setMessages((prev) => {
      const wIdx = prev.findIndex((x) => x.role === 'assistant');
      if (wIdx < 0 || !prev[wIdx].stream) return prev;
      const next = [...prev];
      next[wIdx] = { ...next[wIdx], stream: false };
      return next;
    });
  }, [uiMode]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isOpen]);

  const toggleChat = () => {
    if (!isOpen) {
      // Reset the chat window and clear the server-side session
      setMessages([
        {
          id: 1,
          role: 'assistant',
          content: 'Hi, how can I help you?',
          links: []
        }
      ]);
      setInputValue('');
      setIsLoading(false);
      setSessionId(newSessionId());
      setUiMode('chat');
      setChatClosed(false);
      setBookingCode(null);
      setShowEmailForm(null);
      setEmailInput('');
      setEmailSending(false);
      setEmailSent({});
    }
    setIsOpen(!isOpen);
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!inputValue.trim() || isLoading) return;

    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: inputValue,
      links: []
    };

    const newMessages = [...messages, userMessage];
    setMessages(newMessages);
    setInputValue('');
    setIsLoading(true);

    try {
      const history = messages.map(m => ({
        role: m.role,
        content: m.content
      }));

      const response = await fetch(API_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: userMessage.content,
          history: history,
          session_id: sessionId  // echo back existing session, or null for first turn
        })
      });

      if (!response.ok) {
        throw new Error('Network response was not ok');
      }

      const data = await response.json();

      // Store the session_id returned by the Orchestrator for subsequent turns
      if (data.session_id) {
        setSessionId(data.session_id);
      }

      // Handle chat_closed flag from Phase 4 booking
      if (data.chat_closed) {
        setChatClosed(true);
        setBookingCode(data.booking_code || null);
      }

      const botMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: data.text || "Sorry, I couldn't understand that.",
        links: data.links || [],
        type: data.type,
        bookingCode: data.booking_code || null,
        stream: false,
      };

      setMessages([...newMessages, botMessage]);
    } catch (error) {
      console.error("Chat error:", error);
      const errorMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: "Sorry, I'm having trouble connecting right now.",
        links: [],
        stream: false,
      };
      setMessages([...newMessages, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  // Handle "Send me the booking details" email submission
  const handleSendDetails = async (messageId) => {
    if (!emailInput.trim() || emailSending) return;
    setEmailSending(true);
    try {
      const response = await fetch(SEND_DETAILS_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          booking_code: bookingCode,
          email: emailInput.trim(),
        }),
      });
      const data = await response.json();
      if (data.success) {
        setEmailSent(prev => ({ ...prev, [messageId]: true }));
        setShowEmailForm(null);
      } else {
        alert('Failed to send email. Please try again.');
      }
    } catch (error) {
      console.error('Send details error:', error);
      alert('Failed to send email. Please try again.');
    } finally {
      setEmailSending(false);
    }
  };

  const onVoiceUserTranscript = useCallback((text) => {
    setMessages((prev) => [...prev, { id: Date.now(), role: 'user', content: text, links: [] }]);
  }, []);

  const onVoiceAssistantMessage = useCallback((text, stream) => {
    setMessages((prev) => [
      ...prev,
      {
        id: Date.now(),
        role: 'assistant',
        content: text,
        links: [],
        stream: Boolean(stream),
      },
    ]);
  }, []);

  const onVoiceCallComplete = useCallback((payload) => {
    setChatClosed(true);
    setBookingCode(payload.booking_code || null);
  }, []);

  return (
    <div className="chatbot-wrapper">
      {isOpen && <div className="chatbot-backdrop" onClick={toggleChat} />}

      <div className={`chatbot-window ${isOpen ? 'open' : ''} ${!isDark ? 'light' : ''}`}>
        <div className="chatbot-header">
          <div className="chatbot-header-left">
            <button className="chatbot-back-btn" onClick={toggleChat}>
              <X size={18} />
            </button>
            <div className="chatbot-avatar-badge">
              <Bot size={18} />
            </div>
            <div className="chatbot-title-group">
              <div className="chatbot-title">Groww AI</div>
              <div className="chatbot-status">
                <span className="status-dot"></span>
                Ready
              </div>
            </div>
          </div>
          <div className="chatbot-mode-tabs">
            <button
              type="button"
              className={`mode-tab ${uiMode === 'chat' ? 'active' : ''}`}
              onClick={() => setUiMode('chat')}
            >
              <MessageSquare size={14} />
              Chat
            </button>
            <button
              type="button"
              className={`mode-tab ${uiMode === 'voice' ? 'active' : ''}`}
              onClick={() => {
                if (chatClosed) return;
                setVoiceConnectReady(false);
                setMessages((prev) => {
                  const wIdx = prev.findIndex((x) => x.role === 'assistant');
                  if (wIdx < 0) return prev;
                  const next = [...prev];
                  next[wIdx] = { ...next[wIdx], stream: true };
                  return next;
                });
                setUiMode('voice');
              }}
              disabled={chatClosed}
              title={chatClosed ? 'Session ended' : 'Voice mode'}
            >
              <Mic size={14} />
              Voice
            </button>
          </div>
        </div>

        <div className="chatbot-messages">
          {messages.map((msg) => (
            <div key={msg.id} className={`message-row ${msg.role}`}>
              <div className={`message-bubble ${msg.role} ${msg.type === 'refuse' ? 'refusal' : ''} ${msg.type === 'booking' ? 'booking-confirm' : ''}`}>
                {msg.role === 'assistant' ? (
                  <TypewriterMessage
                    content={msg.content}
                    stream={Boolean(msg.stream)}
                    onAnimationComplete={
                      uiMode === 'voice' &&
                      !voiceConnectReady &&
                      firstAssistantId != null &&
                      msg.id === firstAssistantId
                        ? handleVoiceIntroAnimationDone
                        : undefined
                    }
                  />
                ) : (
                  <p>{msg.content}</p>
                )}

                {msg.links && msg.links.length > 0 && (
                  <div className="message-links">
                    {msg.links.map((link, idx) => (
                      <a
                        key={idx}
                        href={link.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="source-link"
                      >
                        <ExternalLink size={10} />
                        {link.label}
                      </a>
                    ))}
                  </div>
                )}

                {/* "Send me the booking details" button — shown for booking confirmations */}
                {msg.type === 'booking' && msg.bookingCode && (
                  <div className="booking-actions">
                    {emailSent[msg.id] ? (
                      <div className="email-sent-badge">
                        <Check size={14} />
                        Details sent!
                      </div>
                    ) : showEmailForm === msg.id ? (
                      <div className="email-form">
                        <div className="email-form-row">
                          <Mail size={14} className="email-icon" />
                          <input
                            type="email"
                            value={emailInput}
                            onChange={(e) => setEmailInput(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && handleSendDetails(msg.id)}
                            placeholder="your@email.com"
                            disabled={emailSending}
                          />
                          <button
                            onClick={() => handleSendDetails(msg.id)}
                            disabled={!emailInput.trim() || emailSending}
                            className="email-send-btn"
                          >
                            {emailSending ? <RefreshCw size={14} className="spin-icon" /> : 'Send'}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        className="send-details-btn"
                        onClick={() => setShowEmailForm(msg.id)}
                      >
                        <Mail size={14} />
                        Send me the booking details
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
          
          {isLoading && (
            <div className="message-row assistant">
              <div className="message-bubble assistant loading-bubble">
                <RefreshCw size={14} className="spin-icon" />
                Thinking...
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input area — disabled when chat is closed after booking */}
        {chatClosed ? (
          <div className="chatbot-session-ended">
            <div className="session-ended-text">Session ended</div>
            <button className="session-ended-close-btn" onClick={toggleChat}>
              Close
            </button>
          </div>
        ) : uiMode === 'voice' ? (
          <VoicePanel
            sessionId={sessionId}
            disabled={!isOpen}
            connectEnabled={voiceConnectReady}
            voiceStartedWithHistory={messages.some((m) => m.role === 'user')}
            onUserTranscript={onVoiceUserTranscript}
            onAssistantMessage={onVoiceAssistantMessage}
            onVoiceCallComplete={onVoiceCallComplete}
          />
        ) : (
          <form className="chatbot-input-area" onSubmit={handleSendMessage}>
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Message..."
              disabled={isLoading}
            />
            <button type="submit" disabled={!inputValue.trim() || isLoading}>
              <Send size={18} />
            </button>
          </form>
        )}
      </div>

      <button className={`chatbot-fab ${isOpen ? 'hidden' : ''}`} onClick={toggleChat}>
        <Sparkles size={24} />
      </button>
    </div>
  );
};

export default Chatbot;
