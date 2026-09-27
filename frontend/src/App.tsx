import { Navigate, Route, Routes } from 'react-router'
import { AuthProvider } from './auth/AuthProvider'
import { RequireAuth } from './auth/RequireAuth'
import { AppShell } from './components/AppShell'
import { LoginPage } from './pages/LoginPage'
import { OpportunityDetailPage } from './pages/OpportunityDetailPage'
import { OpportunityFormPage } from './pages/OpportunityFormPage'
import { OpportunityListPage } from './pages/OpportunityListPage'
import { ProfilePage } from './pages/ProfilePage'
import { SourcesPage } from './pages/SourcesPage'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<AppShell />}>
            <Route path="/profile" element={<ProfilePage />} />
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
