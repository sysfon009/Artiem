import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useConfigStore, useUserStore } from '../../stores/useAppStore';
import { getInstructions, getUsers, getUserDetail } from '../../services/api';
import './RightSidebar.css';

export default function RightSidebar({ onClose }) {
  const navigate = useNavigate();
  const config = useConfigStore();
  const { activeUserId, setActiveUser, setUserProfile, users, setUsers } = useUserStore();
  const [instructions, setInstructions] = useState([]);
  const [section, setSection] = useState('persona'); // 'persona' | 'model' | 'params' | 'tools' | 'image'

  // Load instructions
  useEffect(() => {
    (async () => {
      try {
        const res = await getInstructions();
        if (res.status === 'success') setInstructions(res.data || []);
      } catch { /* skip */ }
    })();
  }, []);

  // Load users list
  const loadUsers = useCallback(async () => {
    try {
      const res = await getUsers();
      if (res.status === 'success') setUsers(res.data || []);
    } catch { /* skip */ }
  }, [setUsers]);

  useEffect(() => { loadUsers(); }, [loadUsers]);

  // Select user persona
  const selectUser = async (id) => {
    setActiveUser(id);
    try {
      const res = await getUserDetail(id);
      if (res.status === 'success') setUserProfile(res.data);
    } catch { /* skip */ }
  };

  const updateConfig = (key, value) => {
    config.setConfig({ [key]: value });
  };

  return (
    <div className="right-sidebar">
      <div className="rs-header">
        <h3 className="rs-title">⚙ Configuration</h3>
      </div>

      {/* Section Tabs */}
      <div className="rs-tabs">
        {[
          { key: 'persona', icon: '👤', label: 'User' },
          { key: 'model', icon: '🤖', label: 'Model' },
          { key: 'params', icon: '🎛', label: 'Params' },
          { key: 'tools', icon: '🔧', label: 'Tools' },
          { key: 'image', icon: '🎨', label: 'Image' },
        ].map(s => (
          <button key={s.key} className={`rs-tab ${section === s.key ? 'active' : ''}`} onClick={() => setSection(s.key)}>
            {s.icon}
            <span>{s.label}</span>
          </button>
        ))}
      </div>

      <div className="rs-content">
        {/* User Persona Section */}
        {section === 'persona' && (
          <div className="rs-section animate-fade">
            <div className="rs-group">
              <label className="rs-label">Active Persona</label>
              <div className="rs-user-list">
                {users.map(userItem => {
                  const user = typeof userItem === 'string'
                    ? { id: userItem, name: userItem.replace(/_/g, ' '), avatar: null }
                    : userItem;
                  return (
                    <div
                      key={user.id}
                      className={`rs-user-item ${user.id === activeUserId ? 'active' : ''}`}
                      onClick={() => selectUser(user.id)}
                    >
                      {user.avatar ? (
                        <img src={`/assets/user_profiles/${user.id}/${user.avatar}`} alt="" className="rs-user-avatar" style={{ border: 'none', objectFit: 'cover' }} />
                      ) : (
                        <div className="rs-user-avatar">{(user.name || '?')[0]?.toUpperCase()}</div>
                      )}
                      <span className="rs-user-name">{user.name || 'Unknown User'}</span>
                      {user.id === activeUserId && <span className="rs-user-badge">✓</span>}
                      <button className="rs-user-edit" onClick={(e) => { e.stopPropagation(); navigate(`/roleplay/user/edit/${user.id}`); }} title="Edit">
                        ✎
                      </button>
                    </div>
                  );
                })}
                {users.length === 0 && (
                  <div className="rs-empty">No user personas yet</div>
                )}
              </div>
            </div>
            <button className="rs-new-btn" onClick={() => navigate('/roleplay/user/edit')}>
              + New Persona
            </button>
            {activeUserId && (
              <button className="rs-clear-btn" onClick={() => { setActiveUser(null); setUserProfile(null); }}>
                Clear Active Persona
              </button>
            )}
          </div>
        )}

        {/* Model Section */}
        {section === 'model' && (
          <div className="rs-section animate-fade">
            <div className="rs-group">
              <label className="rs-label">Model Version</label>
              <div className="rs-radio-group">
                {[
                  { value: 'logic_v1', label: 'Testing', desc: 'Single Node Testing' },
                  { value: 'logic_v2', label: 'Enhanced Testing', desc: 'Multiple System' },
                  { value: 'logic_v3', label: 'For Image', desc: 'Image Testing' },
                  { value: 'logic_beta', label: 'Beta', desc: 'Stable Version' },
                  { value: 'logic_v4', label: 'Agentic', desc: '5-Phase Pipeline' },
                ].map(opt => (
                  <label key={opt.value} className={`rs-radio ${config.modelVersion === opt.value ? 'active' : ''}`}>
                    <input type="radio" name="model" value={opt.value}
                      checked={config.modelVersion === opt.value}
                      onChange={() => updateConfig('modelVersion', opt.value)} />
                    <div>
                      <span className="rs-radio-label">{opt.label}</span>
                      <span className="rs-radio-desc">{opt.desc}</span>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <div className="rs-group">
              <label className="rs-label">Instruction Set</label>
              <select className="rs-select" value={config.instructionName} onChange={(e) => updateConfig('instructionName', e.target.value)}>
                <option value="">Default</option>
                {instructions.map(name => <option key={name} value={name}>{name}</option>)}
              </select>
            </div>
          </div>
        )}

        {/* Parameters Section */}
        {section === 'params' && (
          <div className="rs-section animate-fade">
            <SliderControl label="Max Output Tokens" value={config.maxTokens} min={1000} max={200000} step={1000}
              onChange={(v) => updateConfig('maxTokens', v)} displayValue={config.maxTokens.toLocaleString()} />

            <SliderControl label="Temperature" value={config.temperature} min={0} max={2} step={0.05}
              onChange={(v) => updateConfig('temperature', v)} displayValue={config.temperature.toFixed(2)} />

            <SliderControl label="Top P" value={config.topP} min={0} max={1} step={0.01}
              onChange={(v) => updateConfig('topP', v)} displayValue={config.topP.toFixed(2)} />

            <SliderControl label="Top K" value={config.topK} min={1} max={100} step={1}
              onChange={(v) => updateConfig('topK', v)} displayValue={config.topK} />
          </div>
        )}

        {/* Tools Section */}
        {section === 'tools' && (
          <div className="rs-section animate-fade">
            <div className="rs-group">
              <label className="rs-toggle-row">
                <span className="rs-toggle-text">
                  <strong>Google Search</strong>
                  <span className="rs-toggle-desc">Allow AI to search the web</span>
                </span>
                <div className={`rs-switch ${config.useSearch ? 'on' : ''}`} onClick={() => updateConfig('useSearch', !config.useSearch)}>
                  <div className="rs-switch-thumb" />
                </div>
              </label>
            </div>

            <div className="rs-group">
              <label className="rs-toggle-row">
                <span className="rs-toggle-text">
                  <strong>Code Execution</strong>
                  <span className="rs-toggle-desc">Allow AI to run Python code</span>
                </span>
                <div className={`rs-switch ${config.useCode ? 'on' : ''}`} onClick={() => updateConfig('useCode', !config.useCode)}>
                  <div className="rs-switch-thumb" />
                </div>
              </label>
            </div>
          </div>
        )}

        {/* Image Section */}
        {section === 'image' && (
          <div className="rs-section animate-fade">
            <div className="rs-group">
              <label className="rs-label">Aspect Ratio</label>
              <select className="rs-select"
                value={config.imageSettings?.aspect_ratio || 'Auto'}
                onChange={(e) => updateConfig('imageSettings', { ...config.imageSettings, aspect_ratio: e.target.value })}>
                {['Auto', '1:1', '16:9', '9:16', '3:4', '4:3', '3:2', '2:3'].map(r => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>

            <div className="rs-group">
              <label className="rs-label">Resolution</label>
              <select className="rs-select"
                value={config.imageSettings?.resolution || 'Auto'}
                onChange={(e) => updateConfig('imageSettings', { ...config.imageSettings, resolution: e.target.value })}>
                {['Auto', '1k', '2k', '3k', '4k'].map(r => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SliderControl({ label, value, min, max, step, onChange, displayValue }) {
  return (
    <div className="rs-group">
      <div className="rs-slider-header">
        <label className="rs-label">{label}</label>
        <span className="rs-value">{displayValue}</span>
      </div>
      <input type="range" className="rs-slider" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  );
}
