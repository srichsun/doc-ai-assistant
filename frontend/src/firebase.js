// Firebase client: Google sign-in and ID tokens for the browser.
//
// The config here is public (it ships in every web app's bundle) — real
// security comes from Firebase Auth plus the backend verifying each token.
// Values are read from Vite env vars (see .env / .env.example).
import { initializeApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  onAuthStateChanged,
  signInWithRedirect,
  signOut,
} from "firebase/auth";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const provider = new GoogleAuthProvider();

export function signInWithGoogle() {
  // Redirect (not popup) is far more reliable on mobile browsers.
  return signInWithRedirect(auth, provider);
}

export function signOutUser() {
  return signOut(auth);
}

// Call cb(user) whenever sign-in state changes; returns an unsubscribe fn.
export function onAuthChange(cb) {
  return onAuthStateChanged(auth, cb);
}

// A fresh ID token for the current user, or null if signed out.
export async function getIdToken() {
  return auth.currentUser ? auth.currentUser.getIdToken() : null;
}
