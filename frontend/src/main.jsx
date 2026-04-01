import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// Auto-refresh mechanism to ensure latest UI on boot without clearing localStorage
const CURRENT_VERSION = "1.0.2"; // Bump version for aggressive cache busting
const savedVersion = localStorage.getItem('rmix_app_version');

if (savedVersion !== CURRENT_VERSION) {
  console.log('App updated! Forcing aggressive refresh to load latest UI assets...');
  localStorage.setItem('rmix_app_version', CURRENT_VERSION);
  // Aggressive cache bust: append timestamp to URL to physically bypass browser cache
  window.location.href = window.location.pathname + '?v=' + new Date().getTime();
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
// test  
