// Import Firebase app initialization and authentication function
import { initializeApp } from "https://www.gstatic.com/firebasejs/12.10.0/firebase-app.js";
import { getAuth } from "https://www.gstatic.com/firebasejs/12.10.0/firebase-auth.js";

// Firebase project settings
const firebaseConfig = {
    apiKey: "AIzaSyCtNRyqhNCWxmVy83lAfUrcUw3a8rzbBx0",
    authDomain: "wameed-4c9ef.firebaseapp.com",
    projectId: "wameed-4c9ef",
    storageBucket: "wameed-4c9ef.firebasestorage.app",
    messagingSenderId: "614908637534",
    appId: "1:614908637534:web:b876f54c5b0a3a79b7dfcf",
    measurementId: "G-4V0Z2JDEV1"
  };

// Initialize Firebase
const app = initializeApp(firebaseConfig); 
const auth = getAuth(app);

export { app, auth }; // export app and auth so other files can use them