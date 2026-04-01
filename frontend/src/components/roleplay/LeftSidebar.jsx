import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCharacterStore, useSessionStore, useChatStore } from '../../stores/useAppStore';
import { getCharacters, getCharacterDetail, getHistorySessions, deleteHistorySession, getChatHistory } from '../../services/api';
import './LeftSidebar.css';

export default function LeftSidebar({ onClose }) {
  const navigate = useNavigate();
  const { activeCharId, setActiveChar, setCharProfile, characters, setCharacters } = useCharacterStore();
  const { activeSessionId, setActiveSession, sessions, setSessions, setNewChatMode, isNewChatMode } = useSessionStore();
  const { messages, setMessages } = useChatStore();

  const [tab, setTab] = useState('characters'); // 'characters' | 'sessions'
  const [charDetails, setCharDetails] = useState({}); // cache: { id: profile }
  const [loading, setLoading] = useState(true);

  const estimatedTokens = useMemo(() => {
    if (!activeCharId || isNewChatMode || !activeSessionId) return 0;
    let totalChars = 0;
    messages.forEach(msg => {
      let textContent = "";
      if (msg.parts) {
        if (Array.isArray(msg.parts)) {
          textContent = msg.parts.map(p => {
            if (typeof p === 'object' && p !== null) {
              return p.text || p.executable_code?.code || ""; 
            }
            return String(p);
          }).join(" ");
        } else {
          textContent = String(msg.parts);
        }
      } 
      else if (msg.content) {
        textContent = String(msg.content);
      }
      if (msg.streamText) {
        textContent += " " + msg.streamText;
      }
      if (msg.thoughts) {
        textContent += " " + msg.thoughts;
      }
      if (textContent) {
        totalChars += textContent.length;
      }
    });
    return Math.ceil(totalChars / 4);
  }, [messages, activeCharId, activeSessionId, isNewChatMode]);

  // Load characters
  const loadCharacters = useCallback(async () => {
    try {
      const res = await getCharacters();
      if (res.status === 'success') setCharacters(res.data || []);
    } catch (e) { console.error('Load chars failed:', e); }
  }, [setCharacters]);

  // Load sessions for active char
  const loadSessions = useCallback(async () => {
    if (!activeCharId) return;
    try {
      const res = await getHistorySessions(activeCharId);
      if (res.status === 'success') setSessions(res.data || []);
    } catch (e) { console.error('Load sessions failed:', e); }
  }, [activeCharId, setSessions]);

  // Load character detail (with cache)
  const loadCharDetail = useCallback(async (id) => {
    if (charDetails[id]) return charDetails[id];
    try {
      const res = await getCharacterDetail(id);
      if (res.status === 'success') {
        setCharDetails(prev => ({ ...prev, [id]: res.data }));
        return res.data;
      }
    } catch { /* skip */ }
    return null;
  }, [charDetails]);

  useEffect(() => {
    (async () => {
      setLoading(true);
      await loadCharacters();
      setLoading(false);
    })();
  }, [loadCharacters]);

  useEffect(() => {
    if (activeCharId) loadSessions();
  }, [activeCharId, loadSessions]);

  // Select character → auto-switch to Sessions tab
  const selectCharacter = async (id) => {
    if (id === activeCharId) {
      // Already selected — just switch to sessions
      setTab('sessions');
      return;
    }
    setActiveChar(id);
    setMessages([]);
    const detail = await loadCharDetail(id);
    if (detail) setCharProfile(detail);

    // Load latest session & auto-switch tab
    try {
      const sessRes = await getHistorySessions(id);
      if (sessRes.status === 'success') {
        setSessions(sessRes.data || []);
        const active = sessRes.data?.find(s => s.is_active);
        if (active) {
          setActiveSession(active.folder);
          const histRes = await getChatHistory(id, active.folder);
          if (histRes.status === 'success') setMessages(histRes.data || []);
        } else {
          setNewChatMode();
        }
      }
    } catch { setNewChatMode(); }

    setTab('sessions');
    if (onClose) onClose();
  };

  // Select session — only clear & reload if actually changing
  const selectSession = async (folder) => {
    if (folder === activeSessionId && !isNewChatMode) return; // Already on it
    setActiveSession(folder);
    setMessages([]);
    try {
      const res = await getChatHistory(activeCharId, folder);
      if (res.status === 'success') setMessages(res.data || []);
    } catch (e) { console.error('History load failed:', e); }
  };

  // Delete session
  const handleDeleteSession = async (e, folder) => {
    e.stopPropagation();
    if (!confirm('Delete this chat session? This cannot be undone.')) return;
    try {
      await deleteHistorySession({ char_id: activeCharId, session_id: folder });
      // Reload sessions list
      const sessRes = await getHistorySessions(activeCharId);
      if (sessRes.status === 'success') {
        setSessions(sessRes.data || []);
        // If we deleted the active session, switch to new chat unconditionally
        if (folder === activeSessionId) {
          setNewChatMode();
          setMessages([]);
        }
      }
    } catch (err) { console.error('Delete session failed:', err); }
  };

  const startNewChat = () => {
    setNewChatMode();
    setMessages([]);
  };

  return (
    <div className="left-sidebar">
      {/* App branding */}
      <div className="ls-brand" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div className="ls-brand-icon">R</div>
          <span className="ls-brand-text">RMIX</span>
        </div>
        <button 
          onClick={() => window.location.reload(true)} 
          title="Hard Reload App"
          style={{ 
            background: 'none', 
            border: 'none', 
            color: '#94a3b8', 
            cursor: 'pointer', 
            fontSize: '1rem',
            padding: '4px',
            borderRadius: '4px'
          }}
          onMouseOver={(e) => e.currentTarget.style.color = '#e2e8f0'}
          onMouseOut={(e) => e.currentTarget.style.color = '#94a3b8'}
        >
          ↻
        </button>
      </div>

      {/* Tabs — only Characters & Sessions */}
      <div className="ls-tabs">
        <button className={`ls-tab ${tab === 'characters' ? 'active' : ''}`} onClick={() => setTab('characters')}>
          Characters
        </button>
        <button className={`ls-tab ${tab === 'sessions' ? 'active' : ''}`} onClick={() => setTab('sessions')}>
          Sessions
        </button>
      </div>

      {/* Content */}
      <div className="ls-content">
        {loading && <div className="ls-loading">Loading...</div>}

        {/* Characters Tab */}
        {!loading && tab === 'characters' && (
          <>
            <button className="ls-new-btn" onClick={() => navigate('/roleplay/character/edit')}>
              + New Character
            </button>
            <div className="ls-list">
              {characters.map(charItem => {
                const char = typeof charItem === 'string' 
                  ? { id: charItem, name: charItem.replace(/_/g, ' '), avatar: null } 
                  : charItem;
                return (
                  <div
                    key={char.id}
                    className={`ls-item ${char.id === activeCharId ? 'active' : ''}`}
                    onClick={() => selectCharacter(char.id)}
                  >
                    <div className="ls-item-avatar">
                      {charDetails[char.id]?.images?.avatar || char.avatar ? (
                        <img src={`/assets/Characters/${char.id}/${charDetails[char.id]?.images?.avatar || char.avatar}`} alt="" />
                      ) : (
                        <div className="ls-avatar-placeholder">{(charDetails[char.id]?.name || char.name || '?')[0]?.toUpperCase()}</div>
                      )}
                    </div>
                    <div className="ls-item-info">
                      <span className="ls-item-name">{charDetails[char.id]?.name || char.name || 'Unknown Character'}</span>
                    </div>
                    <button className="ls-item-edit" onClick={(e) => { e.stopPropagation(); navigate(`/roleplay/character/edit/${char.id}`); }} title="Edit">
                      ✎
                    </button>
                  </div>
                );
              })}
              {characters.length === 0 && <div className="ls-empty">No characters yet</div>}
            </div>
          </>
        )}

        {/* Sessions Tab */}
        {!loading && tab === 'sessions' && (
          <>
            <button className="ls-new-btn" onClick={startNewChat}>
              + New Chat
            </button>
            {!activeCharId && <div className="ls-empty">Select a character first</div>}
            <div className="ls-list">
              {sessions.map(s => (
                <div
                  key={s.folder}
                  className={`ls-item ${s.folder === activeSessionId && !isNewChatMode ? 'active' : ''}`}
                  onClick={() => selectSession(s.folder)}
                >
                  <div className="ls-item-info">
                    <span className="ls-item-name">{s.name || s.folder.replace(/_/g, ' ')}</span>
                    {s.is_active && <span className="ls-badge">Latest</span>}
                  </div>
                  <button className="ls-item-delete" onClick={(e) => handleDeleteSession(e, s.folder)} title="Delete Session">
                    🗑
                  </button>
                </div>
              ))}
              {activeCharId && sessions.length === 0 && <div className="ls-empty">No sessions yet</div>}
            </div>
          </>
        )}
      </div>

      {/* Active Character Footer */}
      {activeCharId && (
        <div className="ls-footer">
          <div className="ls-footer-user">
            {charDetails[activeCharId]?.images?.avatar ? (
              <img src={`/assets/Characters/${activeCharId}/${charDetails[activeCharId].images.avatar}`} alt="" className="ls-footer-avatar" />
            ) : (
              <div className="ls-avatar-placeholder small">
                {(charDetails[activeCharId]?.name || activeCharId || '?')[0]?.toUpperCase()}
              </div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span>{charDetails[activeCharId]?.name || (activeCharId ? activeCharId.replace(/_/g, ' ') : 'Unknown')}</span>
              {(activeSessionId && !isNewChatMode) ? (
                <span style={{ fontSize: '0.7rem', color: '#64748b', marginTop: '2px' }}>
                  {estimatedTokens.toLocaleString()} est tokens
                </span>
              ) : null}
            </div>
          </div>
          <button 
            className="ls-footer-settings-btn"
            onClick={() => navigate('/roleplay/settings')}
            title="App Settings (API Keys)"
            style={{ 
              background: 'none', 
              border: 'none', 
              color: '#94a3b8', 
              cursor: 'pointer', 
              fontSize: '1.2rem',
              padding: '4px',
              borderRadius: '6px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
            onMouseOver={(e) => { e.currentTarget.style.color = '#e2e8f0'; e.currentTarget.style.backgroundColor = '#334155'; }}
            onMouseOut={(e) => { e.currentTarget.style.color = '#94a3b8'; e.currentTarget.style.backgroundColor = 'transparent'; }}
          >
            ⚙ SETTINGS
          </button>
        </div>
      )}
    </div>
  );
}
