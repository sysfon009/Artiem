import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export const useCharacterStore = create(
  persist(
    (set) => ({
      activeCharId: null,
      charProfile: null,
      characters: [],
      setActiveChar: (id) => set({ activeCharId: id }),
      setCharProfile: (profile) => set({ charProfile: profile }),
      setCharacters: (list) => set({ characters: list }),
    }),
    { name: 'rmix-character' }
  )
);

export const useUserStore = create(
  persist(
    (set) => ({
      activeUserId: null,
      userProfile: null,
      users: [],
      setActiveUser: (id) => set({ activeUserId: id }),
      setUserProfile: (profile) => set({ userProfile: profile }),
      setUsers: (list) => set({ users: list }),
    }),
    { name: 'rmix-user' }
  )
);

export const useSessionStore = create(
  persist(
    (set) => ({
      activeSessionId: null,
      sessions: [],
      isNewChatMode: false,
      setActiveSession: (id) => set({ activeSessionId: id, isNewChatMode: false }),
      setSessions: (list) => set({ sessions: list }),
      setNewChatMode: () => set({ activeSessionId: 'new_chat_mode', isNewChatMode: true }),
    }),
    { name: 'rmix-session' }
  )
);

export const useChatStore = create((set) => ({
  messages: [],
  isGenerating: false,
  pendingAttachments: [],
  setMessages: (msgs) => set({ messages: msgs }),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  appendToLast: (text) =>
    set((s) => {
      const msgs = [...s.messages];
      if (msgs.length > 0) {
        const last = { ...msgs[msgs.length - 1] };
        last.streamText = (last.streamText || '') + text;
        msgs[msgs.length - 1] = last;
      }
      return { messages: msgs };
    }),
  setGenerating: (v) => set({ isGenerating: v }),
  setPendingAttachments: (files) => set({ pendingAttachments: files }),
  clearPending: () => set({ pendingAttachments: [] }),
}));

export const useConfigStore = create(
  persist(
    (set) => ({
      maxTokens: 111000,
      temperature: 1.0,
      topP: 0.95,
      topK: 40,
      modelVersion: 'def',
      instructionName: '',
      useSearch: false,
      useCode: false,
      imageSettings: {},
      setConfig: (patch) => set((s) => ({ ...s, ...patch })),
    }),
    { name: 'rmix-config' }
  )
);
