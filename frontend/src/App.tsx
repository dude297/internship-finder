import { Navigate, Route, Routes } from 'react-router'
import { useAuth } from './auth/context'
import { AuthProvider } from './auth/AuthProvider'
import { RequireAuth } from './auth/RequireAuth'
import { AppShell } from './components/AppShell'
import { InboxPage } from './pages/InboxPage'
import { LandingPage } from './pages/LandingPage'
import { LoginPage } from './pages/LoginPage'
import { MatchProfilePage } from './pages/MatchProfilePage'
import { OpportunityDetailPage } from './pages/OpportunityDetailPage'
import { OpportunityFormPage } from './pages/OpportunityFormPage'
import { OpportunityListPage } from './pages/OpportunityListPage'
import { ProfilePage } from './pages/ProfilePage'
import { ProfileSourcesPage } from './pages/ProfileSourcesPage'
import { SourcesPage } from './pages/SourcesPage'

// Signed-in owners skip the landing page. While the session check is pending or failing, the
// public page renders (auth is unknown, never assumed logged in).
function Home() {
  const { auth } = useAuth()
  return auth.status === 'authenticated' ? (
    <Navigate to="/opportunities" replace />
  ) : (
    <LandingPage />
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<AppShell />}>
            <Route path="/inbox" element={<InboxPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/profile/match" element={<MatchProfilePage />} />
            <Route path="/profile/sources" element={<ProfileSourcesPage />} />
            <Route path="/opportunities" element={<OpportunityListPage />} />
            <Route path="/opportunities/new" element={<OpportunityFormPage />} />
            <Route path="/opportunities/:id" element={<OpportunityDetailPage />} />
            <Route path="/opportunities/:id/edit" element={<OpportunityFormPage />} />
            <Route path="/sources" element={<SourcesPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/opportunities" replace />} />
      </Routes>
    </AuthProvider>
  )
}
