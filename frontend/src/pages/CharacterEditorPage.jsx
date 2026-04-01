import { useState, useEffect, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { getCharacterDetail, saveCharacter, deleteCharacter } from '../services/api';
import { useCharacterStore } from '../stores/useAppStore';
import './EditorPage.css';

export default function CharacterEditorPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const isEdit = !!id;
  const { setActiveChar, setCharProfile } = useCharacterStore();

  const [name, setName] = useState('');
  const [age, setAge] = useState('');
  const [personality, setPersonality] = useState('');
  const [appearance, setAppearance] = useState('');
  const [initialMessage, setInitialMessage] = useState('');
  const [exampleInput, setExampleInput] = useState('');
  const [exampleOutput, setExampleOutput] = useState('');
  const [avatarPreview, setAvatarPreview] = useState(null);
  const [bgPreview, setBgPreview] = useState(null);
  const [saving, setSaving] = useState(false);

  const avatarRef = useRef(null);
  const bgRef = useRef(null);

  useEffect(() => {
    if (isEdit) {
      (async () => {
        try {
          const res = await getCharacterDetail(id);
          if (res.status === 'success') {
            const d = res.data;
            setName(d.name || '');
            setAge(d.age || '');
            setPersonality(d.personality || '');
            setAppearance(d.appearance || '');
            setInitialMessage(d.initial_message || '');
            setExampleInput(d.example_chat?.input || '');
            setExampleOutput(d.example_chat?.output || '');
            if (d.images?.avatar) setAvatarPreview(`/assets/Characters/${id}/${d.images.avatar}`);
            if (d.images?.background) setBgPreview(`/assets/Characters/${id}/${d.images.background}`);
          }
        } catch (e) { console.error('Load character failed:', e); }
      })();
    }
  }, [id, isEdit]);

  const handleAvatarChange = (e) => {
    if (e.target.files?.[0]) {
      setAvatarPreview(URL.createObjectURL(e.target.files[0]));
    }
  };

  const handleBgChange = (e) => {
    if (e.target.files?.[0]) {
      setBgPreview(URL.createObjectURL(e.target.files[0]));
    }
  };

  const handleSave = async () => {
    if (!name.trim()) { alert('Name is required'); return; }
    setSaving(true);
    try {
      const formData = new FormData();
      formData.append('name', name);
      if (isEdit) formData.append('original_id', id);
      formData.append('age', age);
      formData.append('personality', personality);
      formData.append('appearance', appearance);
      formData.append('initial_message', initialMessage);
      formData.append('example_input', exampleInput);
      formData.append('example_output', exampleOutput);
      if (avatarRef.current?.files[0]) formData.append('avatar', avatarRef.current.files[0]);
      if (bgRef.current?.files[0]) formData.append('bg', bgRef.current.files[0]);

      const res = await saveCharacter(formData);
      if (res.status === 'success') {
        navigate('/roleplay');
      } else {
        alert('Error: ' + res.message);
      }
    } catch (e) { alert('Save failed: ' + e.message); }
    setSaving(false);
  };

  const handleDelete = async () => {
    if (!confirm(`Delete character "${name || id}"? This will delete all chat history too. This cannot be undone.`)) return;
    try {
      const res = await deleteCharacter(id);
      if (res.status === 'success') {
        setActiveChar(null);
        setCharProfile(null);
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
        <h2>{isEdit ? 'Edit Character' : 'New Character'}</h2>
        <div style={{ width: 60 }}></div>
      </div>

      <div className="editor-content">
        <div className="editor-form">
          {/* Avatar & BG Upload */}
          <div className="upload-row">
            <div className="upload-group">
              <label className="upload-label">Avatar</label>
              <div className="upload-box round" onClick={() => avatarRef.current?.click()}>
                {avatarPreview ? <img src={avatarPreview} alt="" /> : <span>+</span>}
                <input ref={avatarRef} type="file" accept="image/*" onChange={handleAvatarChange} hidden />
              </div>
            </div>
            <div className="upload-group">
              <label className="upload-label">Background</label>
              <div className="upload-box wide" onClick={() => bgRef.current?.click()}>
                {bgPreview ? <img src={bgPreview} alt="" /> : <span>+ BG</span>}
                <input ref={bgRef} type="file" accept="image/*" onChange={handleBgChange} hidden />
              </div>
            </div>
          </div>

          <div className="form-group">
            <label>Name *</label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Character Name" />
          </div>

          <div className="form-group">
            <label>Age</label>
            <input type="text" value={age} onChange={(e) => setAge(e.target.value)} placeholder="e.g. 25" />
          </div>

          <div className="form-group">
            <label>Personality</label>
            <textarea value={personality} onChange={(e) => setPersonality(e.target.value)} placeholder="Describe personality traits..." rows={4} />
          </div>

          <div className="form-group">
            <label>Appearance</label>
            <textarea value={appearance} onChange={(e) => setAppearance(e.target.value)} placeholder="Describe physical appearance..." rows={3} />
          </div>

          <div className="form-group">
            <label>Initial Message (Greeting)</label>
            <textarea value={initialMessage} onChange={(e) => setInitialMessage(e.target.value)} placeholder="First message when chat starts..." rows={3} />
          </div>

          <div className="form-group">
            <label>Example Input</label>
            <textarea value={exampleInput} onChange={(e) => setExampleInput(e.target.value)} placeholder="Example user message..." rows={2} />
          </div>

          <div className="form-group">
            <label>Example Output</label>
            <textarea value={exampleOutput} onChange={(e) => setExampleOutput(e.target.value)} placeholder="Expected character response..." rows={2} />
          </div>
        </div>
      </div>

      <div className="editor-footer">
        {isEdit && (
          <button className="btn-delete" onClick={handleDelete}>
            🗑 Delete Character
          </button>
        )}
        <div className="footer-spacer" />
        <button className="btn-save" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save Character'}
        </button>
      </div>
    </div>
  );
}
