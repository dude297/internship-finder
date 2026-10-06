import { lazy, Suspense, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router'
import { useAuth } from './auth/context'
import { AuthProvider } from './auth/AuthProvider'
import { RequireAuth } from './auth/RequireAuth'
import { AppShell } from './components/AppShell'
import { LandingPage } from './pages/LandingPage'
import { LoginPage } from './pages/LoginPage'

// Authenticated pages are code-split; landing and login stay in the entry chunk so the logged-out
// first paint stays light. Chunks load from the same origin, so the CSP's script-src 'self' holds.
const ApplicationsPage = lazy(() =>
  import('./pages/ApplicationsPage').then((m) => ({ default: m.ApplicationsPage })),
)
const DashboardPage = lazy(() =>
  import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage })),
)
const InboxPage = lazy(() =>
  import('./pages/InboxPage').then((m) => ({ default: m.InboxPage })),
)
const MatchProfilePage = lazy(() =>
  import('./pages/MatchProfilePage').then((m) => ({ default: m.MatchProfilePage })),
)
const OpportunityDetailPage = lazy(() =>
  import('./pages/OpportunityDetailPage').then((m) => ({
    default: m.OpportunityDetailPage,
  })),
)
const OpportunityFormPage = lazy(() =>
  import('./pages/OpportunityFormPage').then((m) => ({ default: m.OpportunityFormPage })),
)
const OpportunityListPage = lazy(() =>
  import('./pages/OpportunityListPage').then((m) => ({ default: m.OpportunityListPage })),
)
const ProfilePage = lazy(() =>
  import('./pages/ProfilePage').then((m) => ({ default: m.ProfilePage })),
)
const ProfileSourcesPage = lazy(() =>
  import('./pages/ProfileSourcesPage').then((m) => ({ default: m.ProfileSourcesPage })),
)
const RequirementQueuePage = lazy(() =>
  import('./pages/RequirementQueuePage').then((m) => ({
    default: m.RequirementQueuePage,
  })),
)
const SourcesPage = lazy(() =>
  import('./pages/SourcesPage').then((m) => ({ default: m.SourcesPage })),
)

const Lazy = ({ children }: { children: ReactNode }) => (
  <Suspense fallback={<p role="status">Loading…</p>}>{children}</Suspense>
)

// Signed-in owners skip the landing page. While the session check is pending or failing, the
// public page renders (auth is unknown, never assumed logged in).
function Home() {
  const { auth } = useAuth()
  return auth.status === 'authenticated' ? (
    <Navigate to="/dashboard" replace />
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
          <Route
            element={
              <Lazy>
                <AppShell />
              </Lazy>
            }
          >
            <Route
              path="/dashboard"
              element={
                <Lazy>
                  <DashboardPage />
                </Lazy>
              }
            />
            <Route
              path="/applications"
              element={
                <Lazy>
                  <ApplicationsPage />
                </Lazy>
              }
            />
            <Route
              path="/inbox"
              element={
                <Lazy>
                  <InboxPage />
                </Lazy>
              }
            />
            <Route
              path="/profile"
              element={
                <Lazy>
                  <ProfilePage />
                </Lazy>
              }
            />
            <Route
              path="/profile/match"
              element={
                <Lazy>
                  <MatchProfilePage />
                </Lazy>
              }
            />
            <Route
              path="/profile/sources"
              element={
                <Lazy>
                  <ProfileSourcesPage />
                </Lazy>
              }
            />
            <Route
              path="/opportunities"
              element={
                <Lazy>
                  <OpportunityListPage />
                </Lazy>
              }
            />
            <Route
              path="/opportunities/new"
              element={
                <Lazy>
                  <OpportunityFormPage />
                </Lazy>
              }
            />
            <Route
              path="/opportunities/:id"
              element={
                <Lazy>
                  <OpportunityDetailPage />
                </Lazy>
              }
            />
            <Route
              path="/opportunities/:id/edit"
              element={
                <Lazy>
                  <OpportunityFormPage />
                </Lazy>
              }
            />
            <Route
              path="/requirements"
              element={
                <Lazy>
                  <RequirementQueuePage />
                </Lazy>
              }
            />
            <Route
              path="/sources"
              element={
                <Lazy>
                  <SourcesPage />
                </Lazy>
              }
            />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AuthProvider>
  )
}
