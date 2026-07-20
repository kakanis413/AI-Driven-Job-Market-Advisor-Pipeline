import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/instrument-sans'
import '@fontsource-variable/playfair-display/wght-italic.css'
import './index.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
