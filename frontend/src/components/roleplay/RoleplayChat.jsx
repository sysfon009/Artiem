import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useCharacterStore, useUserStore, useSessionStore, useChatStore, useConfigStore } from '../../stores/useAppStore';
import { getChatHistory, chatStream, deleteMessage, uploadFile } from '../../services/api';
import ChatBubble from './ChatBubble';
import './RoleplayChat.css';

export default function RoleplayChat() {
  const { activeCharId, charProfile } = useCharacterStore();
  const { activeUserId, userProfile } = useUserStore();
  const { activeSessionId, isNewChatMode, setActiveSession } = useSessionStore();
  const { messages, setMessages, addMessage, appendToLast, isGenerating, setGenerating, pendingAttachments, setPendingAttachments, clearPending } = useChatStore();
  const config = useConfigStore();

  const [inputText, setInputText] = useState('');
  const chatEndRef = useRef(null);
  const inputRef = useRef(null);
  const fileInputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragCounter = useRef(0);
  const [isGeneratingImage, setIsGeneratingImage] = useState(false);

  // Scroll to bottom
  const scrollToBottom = useCallback(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  // Removed problematic useEffect that auto-fetched history and caused race conditions mid-stream.
  // History is now explicitly fetched by LeftSidebar when clicking a session or character.

  // Removed problematic useEffect that auto-fetched history and caused race conditions mid-stream.
  // History is now explicitly fetched by LeftSidebar when clicking a session or character.

  // Send message
  const sendMessage = async () => {
    const text = inputText.trim();
    if (!text || !activeCharId || isGenerating) return;

    setInputText('');
    setGenerating(true);

    // Process ALL attachments as base64 payload
    let attachmentPayload = undefined;
    if (pendingAttachments.length > 0) {
      try {
        const results = await Promise.all(
          pendingAttachments.map(file =>
            new Promise((resolve, reject) => {
              const reader = new FileReader();
              reader.readAsDataURL(file);
              reader.onload = () => resolve({
                name: file.name,
                data: reader.result.split(',')[1],
                mime_type: file.type || 'image/jpeg'
              });
              reader.onerror = e => reject(e);
            })
          )
        );
        attachmentPayload = results;
      } catch (e) {
        console.error('File read failed:', e);
      }
      clearPending();
    }

    // Add user message to UI immediately
    const userMessageObj = { role: 'user', parts: [{ text }], timestamp: Date.now() / 1000 };
    if (attachmentPayload && attachmentPayload.length > 0) {
      userMessageObj.images = attachmentPayload.map(att => ({
        mime_type: att.mime_type,
        data: att.data
      }));
    }
    
    addMessage(userMessageObj);
    setTimeout(scrollToBottom, 50);

    // Add empty model placeholder for streaming
    addMessage({ role: 'model', parts: [], streamText: '', isStreaming: true, timestamp: Date.now() / 1000 });

    try {
      const payload = {
        character_id: activeCharId,
        user_message: text,
        session_id: isNewChatMode ? 'new_chat_mode' : (activeSessionId || null),
        user_id: activeUserId || null,
        instruction_name: config.instructionName,
        use_search: config.useSearch,
        use_code: config.useCode,
        max_tokens: config.maxTokens,
        temperature: config.temperature,
        top_p: config.topP,
        top_k: config.topK,
        model_version: config.modelVersion,
        attachment: attachmentPayload,
        image_settings: config.imageSettings || {},
      };

      for await (const chunk of chatStream(payload)) {
        if (chunk.session_id) {
          // Hanya set active session, biarkan getHistorySessions & getChatHistory nunggu finalizer biar ga nabrak map
          setActiveSession(chunk.session_id);
          continue;
        }

        switch (chunk.type) {
          case 'generating_image':
            setIsGeneratingImage(true);
            scrollToBottom();
            break;
          case 'text':
            if (chunk.content.includes('![Generated Image]')) setIsGeneratingImage(false);
            appendToLast(chunk.content);
            scrollToBottom();
            break;
          case 'thought':
            // Store thoughts separately
            useChatStore.setState(s => {
              const msgs = [...s.messages];
              if (msgs.length > 0) {
                const last = { ...msgs[msgs.length - 1] };
                last.thoughts = (last.thoughts || '') + chunk.content;
                msgs[msgs.length - 1] = last;
              }
              return { messages: msgs };
            });
            break;
          case 'image':
            useChatStore.setState(s => {
              const msgs = [...s.messages];
              if (msgs.length > 0) {
                let last = { ...msgs[msgs.length - 1] };
                if (last.role !== 'model') {
                  msgs.push({ role: 'model', parts: [], images: [chunk.content], isStreaming: true, timestamp: Date.now() / 1000 });
                } else {
                  last.images = [...(last.images || []), chunk.content];
                  msgs[msgs.length - 1] = last;
                }
              }
              return { messages: msgs };
            });
            scrollToBottom();
            break;
          case 'executable_code':
            appendToLast(`\n\n\`\`\`${chunk.content.language || 'python'}\n${chunk.content.code}\n\`\`\`\n\n`);
            scrollToBottom();
            break;
          case 'code_execution_result':
            appendToLast(`\n\n---\n\n**Code Execution Result:**\n\`\`\`text\n${chunk.content.output || chunk.content.outcome}\n\`\`\`\n\n---\n\n`);
            scrollToBottom();
            break;
          case 'signal':
            if (chunk.content === 'done') {
              setIsGeneratingImage(false);
              useChatStore.setState(s => {
                const msgs = [...s.messages];
                if (msgs.length > 0) {
                  const last = { ...msgs[msgs.length - 1] };
                  last.isStreaming = false;
                  msgs[msgs.length - 1] = last;
                }
                return { messages: msgs };
              });
            }
            break;
          case 'error':
            appendToLast(`\n\n⚠️ Error: ${chunk.content}`);
            break;
        }
      }
    } catch (e) {
      appendToLast(`\n\n⚠️ Connection error: ${e.message}`);
      console.error('Chat error:', e);
    } finally {
      setGenerating(false);
      scrollToBottom();
      
      // Auto-refresh history to sync backend mappings (grouped bubbles/images)
      // Merge streaming thought data into server response to prevent thought loss
      const currentSession = useSessionStore.getState().activeSessionId;
      if (currentSession && currentSession !== 'new_chat_mode') {
        getChatHistory(activeCharId, currentSession).then(res => {
          if (res.status === 'success') {
            const serverMsgs = res.data || [];
            // Preserve thought data from streaming that might not be in server format
            const currentMsgs = useChatStore.getState().messages;
            const lastStreamMsg = currentMsgs.length > 0 ? currentMsgs[currentMsgs.length - 1] : null;
            
            if (lastStreamMsg && lastStreamMsg.thoughts && serverMsgs.length > 0) {
              // Find the last model message in server data and attach streaming thoughts
              for (let i = serverMsgs.length - 1; i >= 0; i--) {
                if (serverMsgs[i].role === 'model') {
                  // Only attach if server msg doesn't already have thought data from parts
                  const hasParts = Array.isArray(serverMsgs[i].parts) && 
                    serverMsgs[i].parts.some(p => typeof p === 'object' && p?.thought === true);
                  if (!hasParts && !serverMsgs[i].thoughts) {
                    serverMsgs[i].thoughts = lastStreamMsg.thoughts;
                  }
                  break;
                }
              }
            }
            setMessages(serverMsgs);
          }
        }).catch(err => console.error('Auto-refresh failed:', err));
        
        // Also refresh the session list so LeftSidebar displays the newly minted session
        import('../../services/api').then(({ getHistorySessions }) => {
          getHistorySessions(activeCharId).then(res => {
            if (res.status === 'success') useSessionStore.getState().setSessions(res.data || []);
          });
        });
      }
    }
  };

  // Delete message
  const handleDelete = async (index) => {
    if (!confirm('Delete this message and all below?')) return;
    try {
      await deleteMessage({ character_id: activeCharId, index, session_id: activeSessionId });
      // Reload history safely
      import('../../services/api').then(({ getChatHistory }) => {
        getChatHistory(activeCharId, activeSessionId).then(res => {
          if (res.status === 'success') setMessages(res.data || []);
        });
      });
    } catch (e) { console.error('Delete failed:', e); }
  };

  // Handle file drop — using counter to prevent child-element flickering
  const handleDragEnter = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current++;
    if (dragCounter.current === 1) {
      setIsDragging(true);
    }
  };
  const handleDragOver = (e) => { e.preventDefault(); };
  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current--;
    if (dragCounter.current <= 0) {
      dragCounter.current = 0;
      setIsDragging(false);
    }
  };
  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current = 0;
    setIsDragging(false);
    if (e.dataTransfer.files.length > 0) {
      const newFiles = Array.from(e.dataTransfer.files);
      setPendingAttachments([...pendingAttachments, ...newFiles]);
    }
  };

  const handleFileSelect = (e) => {
    if (e.target.files.length > 0) {
      const newFiles = Array.from(e.target.files);
      setPendingAttachments([...pendingAttachments, ...newFiles]);
      e.target.value = ''; // reset so same files can be re-selected
    }
  };

  const removePendingAttachment = (indexToRemove) => {
    setPendingAttachments(pendingAttachments.filter((_, i) => i !== indexToRemove));
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleInputChange = (e) => {
    setInputText(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 150) + 'px';
  };

  const { groupedMessages, charAvatar, userAvatar } = useMemo(() => {
    const displayMessages = [];
    if (charProfile?.initial_message) {
      const hasModelFirst = messages.length > 0 && messages[0]?.role === 'model';
      if (messages.length === 0 || !hasModelFirst) {
        displayMessages.push({ role: 'model', parts: [charProfile.initial_message], isGreeting: true });
      }
    }
    displayMessages.push(...messages);

    const ca = charProfile?.images?.avatar
      ? `/assets/Characters/${activeCharId}/${charProfile.images.avatar}`
      : null;
    const ua = userProfile?.avatar
      ? `/assets/user_profiles/${activeUserId}/${userProfile.avatar}`
      : null;

    const grouped = [];
    const hasModelFirst = messages.length > 0 && messages[0]?.role === 'model';
    const greetingOffset = (charProfile?.initial_message && !hasModelFirst) ? 1 : 0;

    // 👇 PENAMPUNG GAMBAR SEMENTARA 👇
    let pendingToolImages = [];

    for (let i = 0; i < displayMessages.length; i++) {
      const rawMsg = displayMessages[i];
      
      const msg = { 
        ...rawMsg, 
        parts: (Array.isArray(rawMsg.parts) ? rawMsg.parts : [rawMsg.parts]).map(p => {
          if (typeof p === 'object' && p !== null) {
            if (p.executable_code) {
              return `\n\n\`\`\`${p.executable_code.language || 'python'}\n${p.executable_code.code}\n\`\`\`\n\n`;
            }
          }
          return p;
        })
      };
      
      const actualIndex = msg.isGreeting ? -1 : i - greetingOffset;
      msg.originalIndex = actualIndex;

     
      const isToolResponse = msg.role === 'user' && msg.parts.some(p => typeof p === 'object' && p !== null && (p.functionResponse || p.code_execution_result));
      
      if (isToolResponse) {
        
        msg.parts.forEach(p => {
          if (typeof p === 'object' && p !== null && p.functionResponse && p.functionResponse.name === 'generate_image') {
            const fileName = p.functionResponse.response?.display_name;
            if (fileName) {
               
               pendingToolImages = [fileName]; 
            }
          }
        });
        
        
        continue; 
      }
      
      
      if (msg.role === 'model') {
         if (pendingToolImages.length > 0) {
            msg.images = [...(msg.images || []), ...pendingToolImages];
           
            pendingToolImages = []; 
         }
      }

      if (msg.role === 'model' && grouped.length > 0) {
        const parent = grouped[grouped.length - 1];
        if (parent.role === 'model' && parent.isGroupedTool) {
          if (msg.thoughts) parent.thoughts = (parent.thoughts ? parent.thoughts + '\n\n' : '') + msg.thoughts;
          if (msg.images) {
             parent.images = parent.images || [];
             parent.images.push(...msg.images);
          }
          if (msg.codeBlocks) {
             parent.codeBlocks = parent.codeBlocks || [];
             parent.codeBlocks.push(...msg.codeBlocks);
          }
          if (msg.streamText) {
             parent.streamText = (parent.streamText || '') + msg.streamText;
          }
          if (msg.parts) {
             parent.parts.push(...msg.parts);
          }
          if (msg.isStreaming) parent.isStreaming = true;
          else parent.isStreaming = false;
          continue;
        }
      }

      grouped.push(msg);
    }

    return { groupedMessages: grouped, charAvatar: ca, userAvatar: ua };
  }, [messages, charProfile, activeCharId, userProfile, activeUserId]);

  return (
    <div
      className="rp-chat"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Background layer */}
      {charProfile?.images?.background && (
        <div className="chat-bg" style={{
          backgroundImage: `url('/assets/Characters/${activeCharId}/${charProfile.images.background}')`
        }} />
      )}

      {/* Drag overlay */}
      {isDragging && (
        <div className="drag-overlay">
          <div className="drag-content">
            <span className="drag-icon">📎</span>
            <span>Drop file here</span>
          </div>
        </div>
      )}

      {/* Chat messages */}
      <div className="chat-messages" id="chat-container">
        {!activeCharId && (
          <div className="chat-empty">
            <div className="empty-icon">💬</div>
            <h3>Select a character to start chatting</h3>
            <p>Choose from the sidebar on the left</p>
          </div>
        )}

        {activeCharId && groupedMessages.length === 0 && (
          <div className="chat-empty">
            <div className="empty-icon">✨</div>
            <h3>Start a conversation</h3>
            <p>Send a message to begin</p>
          </div>
        )}

        {groupedMessages.map((msg, i) => (
          <ChatBubble
            key={`${msg.timestamp || i}-${i}`}
            message={msg}
            index={msg.originalIndex}
            charName={charProfile?.name || 'Character'}
            charAvatar={charAvatar}
            userName={userProfile?.name || 'You'}
            userAvatar={userAvatar}
            onDelete={handleDelete}
            isLast={i === groupedMessages.length - 1}
            isGeneratingImage={isGeneratingImage && i === groupedMessages.length - 1}
            charId={activeCharId}
            sessionId={activeSessionId}
          />
        ))}
        <div ref={chatEndRef} />
      </div>

      {/* Attachment preview */}
      {pendingAttachments.length > 0 && (
        <div className="attachment-bar">
          {pendingAttachments.map((file, i) => (
            <div className="att-chip" key={`${file.name}-${i}`}>
              <span className="att-icon">📄</span>
              <span className="att-name">{file.name}</span>
              <button className="att-remove" onClick={() => removePendingAttachment(i)}>✕</button>
            </div>
          ))}
          {pendingAttachments.length > 1 && (
            <button className="att-clear-all" onClick={clearPending}>Clear All</button>
          )}
        </div>
      )}

      {/* Input area */}
      {activeCharId && (
        <div className="chat-input-area">
          <input type="file" ref={fileInputRef} style={{ display: 'none' }} onChange={handleFileSelect} multiple accept="image/*" />
          <button className="input-btn attach" onClick={() => fileInputRef.current?.click()} title="Attach File">
            +
          </button>
          <textarea
            ref={inputRef}
            className="chat-input"
            value={inputText}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder={`Message ${charProfile?.name || 'Character'}...`}
            rows={1}
            disabled={isGenerating}
          />
          <button
            className={`input-btn send ${isGenerating ? 'disabled' : ''}`}
            onClick={sendMessage}
            disabled={isGenerating}
          >
            {isGenerating ? '⏳' : '➤'}
          </button>
        </div>
      )}
    </div>
  );
} 
