import { useState, useEffect, useCallback, useRef } from 'react';
import LeftSidebar from '../components/roleplay/LeftSidebar';
import RoleplayChat from '../components/roleplay/RoleplayChat';
import RightSidebar from '../components/roleplay/RightSidebar';
import { useCharacterStore, useUserStore, useSessionStore, useChatStore } from '../stores/useAppStore';
import { getCharacterDetail, getUserDetail, getChatHistory } from '../services/api';
import './RoleplayPage.css';

export default function RoleplayPage() {
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);
  const [mobilePanel, setMobilePanel] = useState('chat'); // 'chat' | 'left' | 'right'

  const { activeUserId, setUserProfile } = useUserStore();
  const { activeCharId, setCharProfile } = useCharacterStore();
  const { activeSessionId, isNewChatMode } = useSessionStore();
  const { setMessages } = useChatStore();

  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth <= 768;
      setIsMobile(mobile);
      if (!mobile) setMobilePanel('chat');
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Initial Data Load (Persisted State Recovery - runs ONCE)
  const initDoneStore = useRef(false);
  
  useEffect(() => {
    if (initDoneStore.current) return;
    initDoneStore.current = true;
    
    // We fetch these once on mount to recover state from Zustand persistence
    if (activeUserId) {
      getUserDetail(activeUserId).then(res => {
        if (res.status === 'success') setUserProfile(res.data);
      }).catch(() => {});
    }

    if (activeCharId) {
      getCharacterDetail(activeCharId).then(res => {
        if (res.status === 'success') setCharProfile(res.data);
      }).catch(() => {});
      
      if (activeSessionId && activeSessionId !== 'new_chat_mode' && !isNewChatMode) {
        getChatHistory(activeCharId, activeSessionId).then(res => {
          if (res.status === 'success') setMessages(res.data || []);
        }).catch(() => {});
      } else if (isNewChatMode || activeSessionId === 'new_chat_mode') {
        setMessages([]);
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleLeft = useCallback(() => {
    if (isMobile) {
      setMobilePanel(p => p === 'left' ? 'chat' : 'left');
    } else {
      setLeftOpen(p => !p);
    }
  }, [isMobile]);

  const toggleRight = useCallback(() => {
    if (isMobile) {
      setMobilePanel(p => p === 'right' ? 'chat' : 'right');
    } else {
      setRightOpen(p => !p);
    }
  }, [isMobile]);

  return (
    <div className="rp-page">
      {/* Mobile Toggle Buttons */}
      {isMobile && (
        <>
          <button className="mobile-toggle left" onClick={toggleLeft} title="Characters">
            {mobilePanel === 'left' ? '✕' : '☰'}
          </button>
          <button className="mobile-toggle right" onClick={toggleRight} title="Settings">
            {mobilePanel === 'right' ? '✕' : '⚙'}
          </button>
        </>
      )}

      {/* Desktop Toggle */}
      {!isMobile && (
        <button
          className={`desktop-toggle ${!leftOpen ? 'collapsed' : ''}`}
          onClick={toggleLeft}
          style={{ left: leftOpen ? 'var(--sidebar-width)' : '0' }}
          title="Toggle Sidebar"
        >
          {leftOpen ? '◂' : '▸'}
        </button>
      )}

      <div className={`rp-layout ${!leftOpen && !isMobile ? 'left-collapsed' : ''} ${!rightOpen && !isMobile ? 'right-collapsed' : ''}`}>
        {/* Left Sidebar */}
        <aside className={`rp-left ${isMobile && mobilePanel !== 'left' ? 'hidden-mobile' : ''}`}>
          <LeftSidebar onClose={() => isMobile && setMobilePanel('chat')} />
        </aside>

        {/* Chat Area */}
        <main className={`rp-center ${isMobile && mobilePanel !== 'chat' ? 'hidden-mobile' : ''}`}>
          <RoleplayChat />
        </main>

        {/* Right Sidebar */}
        <aside className={`rp-right ${isMobile && mobilePanel !== 'right' ? 'hidden-mobile' : ''}`}>
          <RightSidebar onClose={() => isMobile && setMobilePanel('chat')} />
        </aside>
      </div>
    </div>
  );
}
