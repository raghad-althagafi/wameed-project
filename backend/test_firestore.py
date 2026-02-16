from Singleton.firebase_connection import FirebaseConnection
from firebase_admin import firestore

db = FirebaseConnection.get_db()

# write
doc_ref = db.collection("test").document("hello")
doc_ref.set({
    "msg": "Salam from Wameed",
    "time": firestore.SERVER_TIMESTAMP
})

print("✅ Wrote document!")

# read
doc = doc_ref.get()
print("✅ Read back:", doc.to_dict())

# delete
doc_ref.delete()
print("🗑️ Document deleted successfully!")
