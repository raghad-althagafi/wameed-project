// Import Firebase app initialization and authentication function
import { initializeApp } from "https://www.gstatic.com/firebasejs/12.10.0/firebase-app.js";
import { getAuth } from "https://www.gstatic.com/firebasejs/12.10.0/firebase-auth.js";

// Firebase project settings
const firebaseConfig = {
  apiKey: "AIzaSyBmM7rZt-kv3C0CZxw7iWcLxOyJ4CJt1Gg",
  authDomain: "wameed-project-227c2.firebaseapp.com",
  projectId: "wameed-project-227c2",
  storageBucket: "wameed-project-227c2.firebasestorage.app",
  messagingSenderId: "251849817439",
  appId: "1:251849817439:web:6cb6288d3fe46e501fcaea"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig); 
const auth = getAuth(app);

export { app, auth }; // export app and auth so other files can use them