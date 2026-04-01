import { useState, useEffect, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { getUserDetail, saveUser, deleteUser } from '../services/api';
import { useUserStore } from '../stores/useAppStore';
import './EditorPage.css';

export default function UserEditorPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const isEdit = !!id;
  const { activeUserId, setActiveUser, setUserProfile } = useUserStore();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [avatarPreview, setAvatarPreview] = useState(null);
  const [saving, setSaving] = useState(false);

  const avatarRef = useRef(null);

  useEffect(() => {
    if (isEdit) {
      (async () => {
        try {
          const res = await getUserDetail(id);
          if (res.status === 'success') {
            const d = res.data;
            setName(d.name || '');
            setDescription(d.description || '');
            if (d.avatar) setAvatarPreview(`/assets/user_profiles/${id}/${d.avatar}`);
          }
        } catch (e) { console.error('Load user failed:', e); }
      })();
    }
  }, [id, isEdit]);

  const handleAvatarChange = (e) => {
    if (e.target.files?.[0]) {
      setAvatarPreview(URL.createObjectURL(e.target.files[0]));
    }
  };

  const handleSave = async () => {
    if (!name.trim()) { alert('Name is required'); return; }
    setSaving(true);
    try {
      const formData = new FormData();
      formData.append('name', name);
      formData.append('description', description);
      if (isEdit) formData.append('original_id', id);
      if (avatarRef.current?.files[0]) formData.append('avatar', avatarRef.current.files[0]);

      const res = await saveUser(formData);
      if (res.status === 'success') {
        navigate('/roleplay');
      } else {
        alert('Error: ' + res.message);
      }
    } catch (e) { alert('Save failed: ' + e.message); }
    setSaving(false);
  };

  const handleDelete = async () => {
    if (!confirm(`Delete user persona "${name || id}"? This cannot be undone.`)) return;
    try {
      const res = await deleteUser(id);
      if (res.status === 'success') {
        if (activeUserId === id) {
          setActiveUser(null);
          setUserProfile(null);
        }
        navigate('/roleplay');
      } else {
        alert('Delete failed: ' + (res.message || 'Unknown error'));
      }
    } catch (e) { alert('Delete failed: ' + e.message); }
  };

  return (
    <div className="editor-page">
      <div className="editor-header">
        <button className="btn-back" onClick={() => navigate('/roleplay')}>← Back</button>
        <h2>{isEdit ? 'Edit User Persona' : 'New User Persona'}</h2>
        <div style={{ width: 60 }}></div>
      </div>

      <div className="editor-content">
        <div className="editor-form">
          {/* Avatar Upload */}
          <div className="upload-row center">
            <div className="upload-group">
              <label className="upload-label">Avatar</label>
              <div className="upload-box round large" onClick={() => avatarRef.current?.click()}>
                {avatarPreview ? <img src={avatarPreview} alt="" /> : <span>+</span>}
                <input ref={avatarRef} type="file" accept="image/*" onChange={handleAvatarChange} hidden />
              </div>
            </div>
          </div>

          <div className="form-group">
            <label>User Name (Persona) *</label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Captain Alex" />
          </div>

          <div className="form-group">
            <label>Description / User Info</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe yourself to the AI (e.g. 'I am a space explorer looking for...')" rows={5} />
            <span className="form-hint">This information helps the AI understand who they are talking to.</span>
          </div>
        </div>
      </div>

      <div className="editor-footer">
        {isEdit && (
          <button className="btn-delete" onClick={handleDelete}>
            🗑 Delete Persona
          </button>
        )}
        <div className="footer-spacer" />
        <button className="btn-save" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save Persona'}
        </button>
      </div>
    </div>
  );
}
