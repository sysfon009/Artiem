import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getApiKeys, addApiKey, editApiKey, deleteApiKey, assignApiKey } from '../services/api';
import './SettingsPage.css';

export default function SettingsPage() {
  const navigate = useNavigate();
  const [apiKeys, setApiKeys] = useState([]);
  const [assignments, setAssignments] = useState({});
  const [loading, setLoading] = useState(true);
  
  // Form states
  const [editingOldName, setEditingOldName] = useState(null);
  const [newName, setNewName] = useState('');
  const [newKey, setNewKey] = useState('');
  const [vertexLocation, setVertexLocation] = useState('us-central1');
  const [vertexProjectId, setVertexProjectId] = useState('');
  const [keyType, setKeyType] = useState('api_key');
  const [error, setError] = useState('');

  const fetchApiKeys = async () => {
    try {
      setLoading(true);
      const res = await getApiKeys();
      if (res.status === 'success') {
        const payload = res.data; // Now an object: { keys: [...], assignments: {...} }
        setApiKeys(Array.isArray(payload) ? payload : (payload.keys || []));
        setAssignments(payload.assignments || {});
      }
    } catch (err) {
      setError('Failed to load API keys');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchApiKeys();
  }, []);

  const handleAddKey = async (e) => {
    e.preventDefault();
    setError('');
    
    if (keyType === 'api_key') {
      // Allow empty newKey if editing (means keep the old one)
      if (!newName.trim() || (!editingOldName && !newKey.trim())) {
        setError('Name and API Key are required');
        return;
      }
    } else {
      if (!newName.trim() || (!editingOldName && !newKey.trim()) || !vertexLocation.trim() || !vertexProjectId.trim()) {
        setError('Name, JSON Path, Project ID, and Location are required for Vertex AI');
        return;
      }
    }
    
    try {
      setLoading(true);
      let finalKey = newKey.trim() || null;
      if (keyType === 'vertex_ai' && finalKey) {
        finalKey = `VERTEX_AI:${finalKey}|${vertexProjectId.trim()}|${vertexLocation.trim()}`;
      } else if (keyType === 'vertex_ai' && editingOldName) {
        // We still construct the Vertex string so we can update Project ID and Location 
        // even if the path isn't changed. But wait, we can't do that easily without the old path.
        // If the path is empty, we expect them to re-enter it, OR we just require the path if it's vertex_ai.
        // Actually, if it's editing a vertex key, the path is already in the input box because we populate it.
        // So they shouldn't leave it empty.
        if (!finalKey) {
          setError('Path is required for Vertex AI');
          setLoading(false);
          return;
        }
        finalKey = `VERTEX_AI:${finalKey}|${vertexProjectId.trim()}|${vertexLocation.trim()}`;
      }
      
      let res;
      if (editingOldName) {
        res = await editApiKey({ old_name: editingOldName, new_name: newName.trim(), new_key: finalKey });
      } else {
        res = await addApiKey({ name: newName.trim(), key: finalKey });
      }
      
      if (res.status === 'success') {
        resetForm();
        await fetchApiKeys();
      }
    } catch (err) {
      setError(`Failed to ${editingOldName ? 'update' : 'save'} API key`);
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setEditingOldName(null);
    setNewName('');
    setNewKey('');
    setVertexProjectId('');
    setVertexLocation('us-central1');
    setKeyType('api_key');
    setError('');
  };

  const handleEditClick = (keyObj) => {
    setEditingOldName(keyObj.name);
    setNewName(keyObj.name);
    
    if (keyObj.type === 'Vertex AI') {
      setKeyType('vertex_ai');
      setNewKey(keyObj.path || '');
      setVertexProjectId(keyObj.project_id || '');
      setVertexLocation(keyObj.location || 'us-central1');
    } else if (keyObj.type === 'Service Account JSON') {
      // Legacy JSON PATH mapping to Vertex AI fields for UX simplicity
      setKeyType('vertex_ai');
      setNewKey(keyObj.path || '');
      setVertexProjectId('');
      setVertexLocation('us-central1');
    } else {
      setKeyType('api_key');
      setNewKey(''); // Clear secret key, user must re-enter if they want to change it, or leave blank to keep
    }
    
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleDeleteKey = async (name) => {
    if (!window.confirm(`Are you sure you want to delete the API key "${name}"?`)) return;
    setError('');
    try {
      setLoading(true);
      const res = await deleteApiKey({ name });
      if (res.status === 'success') {
        await fetchApiKeys();
      }
    } catch (err) {
      setError('Failed to delete API key');
    } finally {
      setLoading(false);
    }
  };

  const handleAssignKey = async (role, name) => {
    setError('');
    try {
      setLoading(true);
      // If the key is already assigned to the OTHER role, we don't allow it. Alternatively we could unassign the other role automatically, but simple prevention is fine.
      const otherRole = role === 'main_model' ? 'image_model' : 'main_model';
      if (name !== '' && name !== '_unassign' && assignments[otherRole] === name) {
         setError(`Cannot assign to both roles. Key "${name}" is already used by the other model.`);
         setLoading(false);
         return;
      }
      
      const res = await assignApiKey({ role, name });
      if (res.status === 'success') {
        await fetchApiKeys();
      }
    } catch (err) {
      setError('Failed to assign API key');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="settings-page">
      <div className="settings-header">
        <button className="settings-back-btn" onClick={() => navigate('/roleplay')}>
          ← Back
        </button>
        <h1>App Settings</h1>
      </div>

      <div className="settings-content">
        <div className="settings-card">
          <h2>API Keys</h2>
          <p className="settings-desc">Manage API keys securely. They are stored encrypted locally.</p>
          
          {error && <div className="settings-error">{error}</div>}

          <form className="settings-add-form" onSubmit={handleAddKey}>
            <div className="settings-form-header">
              <h3>{editingOldName ? `Editing Key: ${editingOldName}` : 'Add New Key'}</h3>
              {editingOldName && (
                <button type="button" className="settings-cancel-btn" onClick={resetForm} disabled={loading}>
                  Cancel Edit
                </button>
              )}
            </div>
            
            <input 
              type="text" 
              placeholder="API Name (e.g., Gemini Flash)" 
              value={newName} 
              onChange={(e) => setNewName(e.target.value)}
              disabled={loading}
            />
            <select
              value={keyType}
              onChange={(e) => setKeyType(e.target.value)}
              disabled={loading}
              className="settings-key-type-select"
            >
              <option value="api_key">Standard API Key</option>
              <option value="vertex_ai">Vertex AI Credentials (JSON Path)</option>
            </select>
            
            {keyType === 'api_key' ? (
              <input 
                type="password" 
                placeholder={editingOldName ? "Leave blank to keep existing key" : "API Key"} 
                value={newKey} 
                onChange={(e) => setNewKey(e.target.value)}
                disabled={loading}
                className="settings-api-key-input"
              />
            ) : (
              <div className="settings-vertex-inputs">
                <input 
                  type="text" 
                  placeholder="Absolute path to Service Account JSON (e.g., C:\keys\sa.json)" 
                  value={newKey} 
                  onChange={(e) => setNewKey(e.target.value)}
                  disabled={loading}
                />
                <div className="settings-vertex-sub-inputs">
                  <input 
                    type="text" 
                    placeholder="Project ID (e.g., my-project)" 
                    value={vertexProjectId} 
                    onChange={(e) => setVertexProjectId(e.target.value)}
                    disabled={loading}
                  />
                  <input 
                    type="text" 
                    placeholder="Location (e.g., us-central1)" 
                    value={vertexLocation} 
                    onChange={(e) => setVertexLocation(e.target.value)}
                    disabled={loading}
                  />
                </div>
              </div>
            )}
            
            <button type="submit" disabled={loading} className="settings-add-btn">
              {editingOldName ? 'Update Key' : 'Add Key'}
            </button>
          </form>

          <div className="settings-key-list">
            {loading && apiKeys.length === 0 ? (
              <p className="settings-loading">Loading...</p>
            ) : apiKeys.length === 0 ? (
              <p className="settings-empty">No API keys saved yet.</p>
            ) : (
              apiKeys.map(keyObj => {
                // Handle backwards compatibility where keyObj might just be a string
                const name = typeof keyObj === 'string' ? keyObj : keyObj.name;
                const type = typeof keyObj === 'string' ? 'API Key' : keyObj.type;
                
                return (
                  <div key={name} className="settings-key-item">
                    <span className="key-name">{name}</span>
                    <div className="key-actions">
                      <span className="key-status" title={type}>{type} (Encrypted)</span>
                      <button className="key-edit-btn" onClick={() => handleEditClick(keyObj)} disabled={loading}>
                        ✏️ Edit
                      </button>
                      <button className="key-delete-btn" onClick={() => handleDeleteKey(name)} disabled={loading}>
                        🗑 Delete
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          <div className="settings-assignments">
             <h2>Model Assignment</h2>
             <p className="settings-desc">Select which key handles the Main Chat versus Image Generation.</p>
             
             <div className="assignment-row">
               <label>Main Model:</label>
               <select 
                 value={assignments['main_model'] || ''} 
                 onChange={(e) => handleAssignKey('main_model', e.target.value)}
                 disabled={loading}
               >
                 <option value="" disabled>-- Select Key --</option>
                 <option value="_unassign">None (Fallback allowed)</option>
                 {apiKeys.map(k => {
                   const name = typeof k === 'string' ? k : k.name;
                   return <option key={name} value={name}>{name}</option>;
                 })}
               </select>
             </div>

             <div className="assignment-row">
               <label>Image Model (Gemini Pro Image Preview):</label>
               <select 
                 value={assignments['image_model'] || ''} 
                 onChange={(e) => handleAssignKey('image_model', e.target.value)}
                 disabled={loading}
               >
                 <option value="" disabled>-- Select Key --</option>
                 <option value="_unassign">None (Fallback allowed)</option>
                 {apiKeys.map(k => {
                   const name = typeof k === 'string' ? k : k.name;
                   return <option key={name} value={name}>{name}</option>;
                 })}
               </select>
             </div>
          </div>
        </div>
      </div>
    </div>
  );
}
