import React from 'react'
import ReactDOM from 'react-dom/client'
import AppRouter from './AppRouter'
import './index.css'

// Register infrastructure resource handlers (self-registration on import)
import './handlers'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AppRouter />
  </React.StrictMode>,
)
