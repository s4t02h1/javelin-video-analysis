import { BrowserRouter, Route, Routes, Navigate } from 'react-router-dom'

import DashboardPage from './pages/DashboardPage'
import ExpiredPage from './pages/ExpiredPage'
import NotFoundPage from './pages/NotFoundPage'
import BetaTopPage from './pages/BetaTopPage'
import ShootingGuidePage from './pages/ShootingGuidePage'
import UploadPage from './pages/UploadPage'
import DonePage from './pages/DonePage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/dashboard/:token" element={<DashboardPage />} />
        <Route path="/expired" element={<ExpiredPage />} />
        <Route path="/" element={<BetaTopPage />} />
        <Route path="/beta" element={<BetaTopPage />} />
        <Route path="/guide" element={<ShootingGuidePage />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/done" element={<DonePage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  )
}
