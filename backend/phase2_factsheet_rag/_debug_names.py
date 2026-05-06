import chromadb
client = chromadb.PersistentClient(path='chroma_db')
collection = client.get_collection('factsheet_kb')
res = collection.get(include=['metadatas'])
names = sorted(list(set(m.get('scheme_name') for m in res['metadatas'] if m.get('scheme_name'))))
print('Scheme names in DB:')
for n in names:
    print(f'  "{n}"')
