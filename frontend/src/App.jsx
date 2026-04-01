import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import RoleplayPage from './pages/RoleplayPage';
import CharacterEditorPage from './pages/CharacterEditorPage';
import UserEditorPage from './pages/UserEditorPage';
import SettingsPage from './pages/SettingsPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/roleplay" replace />} />
        <Route path="/roleplay" element={<RoleplayPage />} />
        <Route path="/roleplay/character/edit/:id?" element={<CharacterEditorPage />} />
        <Route path="/roleplay/user/edit/:id?" element={<UserEditorPage />} />
        <Route path="/roleplay/settings" element={<SettingsPage />} />
      </Routes>
    </BrowserRouter>
  );
}
