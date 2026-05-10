import { BrowserRouter, Route, Routes, Navigate } from 'react-router-dom'
import DashboardPage from './pages/DashboardPage'
import ExpiredPage from './pages/ExpiredPage'
import NotFoundPage from './pages/NotFoundPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/dashboard/:token" element={<DashboardPage />} />
        <Route path="/expired" element={<ExpiredPage />} />
        <Route path="/" element={<Navigate to="/not-found" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  )
}
