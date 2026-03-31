import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { NavSidebar } from './components/NavSidebar'
import { DashboardHome } from './pages/DashboardHome'
import { LogsPage } from './pages/LogsPage'
import { MeetingDetailPage } from './pages/MeetingDetailPage'
import { MeetingsList } from './pages/MeetingsList'
import { ReviewItemPage } from './pages/ReviewItemPage'
import { ReviewQueuePage } from './pages/ReviewQueuePage'
import './styles/dashboard.css'

function isMeetingDetailPath(pathname: string): boolean {
  return /^\/meetings\/[^/]+$/.test(pathname)
}

function AppMain() {
  const { pathname } = useLocation()
  const meetingDetail = isMeetingDetailPath(pathname)
  return (
    <main className={meetingDetail ? 'main main--meeting-detail' : undefined}>
      <Routes>
        <Route path="/" element={<DashboardHome />} />
        <Route path="/meetings" element={<MeetingsList />} />
        <Route path="/meetings/:id" element={<MeetingDetailPage />} />
        <Route path="/review" element={<ReviewQueuePage />} />
        <Route path="/review/item/:itemId" element={<ReviewItemPage />} />
        <Route path="/logs" element={<LogsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </main>
  )
}

function App() {
  return (
    <div className="app-shell">
      <NavSidebar />
      <AppMain />
    </div>
  )
}

export default App
