import { auth } from "./firebase-config.js";
import {
    createUserWithEmailAndPassword,
    signInWithEmailAndPassword,
    sendEmailVerification,
    sendPasswordResetEmail,
    signOut
} from "https://www.gstatic.com/firebasejs/12.10.0/firebase-auth.js";

const API_BASE = "http://127.0.0.1:5000"; // backend base URL

// save current user in localStorage
function saveCurrentUser(firebaseUser, backendUser = null, fallbackName = "مستخدم") {
    localStorage.setItem("currentUser", JSON.stringify({
        uid: firebaseUser.uid, name: backendUser?.User_name || fallbackName }));
}

// remove the currently stored user from localStorage
function clearCurrentUser() {
    localStorage.removeItem("currentUser");
}

// retrieve the current user from localStorage
export function getStoredCurrentUser() {
    try {
        const raw = localStorage.getItem("currentUser");
        return raw ? JSON.parse(raw) : null;
    } catch {
        return null;
    }
}

// function to create a new account
export async function signupWithEmail(name, email, password) {
    // create user in Firebase Authentication
    const userCredential = await createUserWithEmailAndPassword(auth, email, password);
    const user = userCredential.user;

    // set email language to Arabic
    auth.languageCode = "ar";

    // variables to track email verification status
    let verificationEmailSent = false;
    let verificationError = null;

    try {
        // send email verification to the new user
        await sendEmailVerification(user);
        verificationEmailSent = true;
    } catch (error) {
        // save verification email error
        verificationError = error;
        console.error("Verification email error:", error);
    }

    // get Firebase ID token for backend authorization
    const idToken = await user.getIdToken(true);

    // send user name to backend to complete registration
    const res = await fetch(`${API_BASE}/api/auth/register`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${idToken}`
        },
        body: JSON.stringify({ name })
    });

    // convert backend response to JSON
    const data = await res.json();

    // if backend request failed
    if (!res.ok) {
        throw new Error(data.error || "Failed to register user in backend");
    }

    saveCurrentUser(user, data.user, name);

    // return registration result
    return {
        firebaseUser: user,
        backendData: data,
        verificationEmailSent,
        verificationError
    };
}

// function to sign in user
export async function signinWithEmail(email, password) {
    // sign in with Firebase Authentication
    const userCredential = await signInWithEmailAndPassword(auth, email, password);
    const user = userCredential.user;

    // get Firebase ID token
    const idToken = await user.getIdToken(true);

    // send user data to backend
    const res = await fetch(`${API_BASE}/api/auth/me`, {
        method: "GET", // use POST to send new user data
        headers: {
            "Authorization": `Bearer ${idToken}` // send Firebase token for authentication
        }
    });

    // convert backend response to JSON
    const data = await res.json();

    // if backend request failed
    if (!res.ok) {
        throw new Error(data.error || "Failed to load user profile");
    }

    saveCurrentUser(user, data.user, "مستخدم");

    // return user data
    return data;
}

// function to get current user token
export async function getAuthToken(forceRefresh = false) {
    const user = auth.currentUser; // get current logged-in user
    if (!user) return null; // if there is no logged-in user
    return await user.getIdToken(forceRefresh); // return Firebase ID token
}

// function to log out user
export async function logoutUser() {
    await signOut(auth); // sign out from Firebase
    clearCurrentUser();
    // localStorage.removeItem("currentUser"); // remove saved user data from local storage
}

// function to send reset password email
export async function forgotPassword(email) {
    auth.languageCode = "ar"; // set email language to Arabic
    await sendPasswordResetEmail(auth, email); // send password reset email
}