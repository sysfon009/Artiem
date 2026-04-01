# Artiem
A versatile text-based AI and roleplay application powered by the Gemini API, supporting both text and image interactions. (still in development, but you already can try)

**RMIX** (previous name) is a multi-pipeline AI chat application powered by Google Gemini. It provides text conversations, image generation, and an agentic system that intelligently routes between text and image models — all through a clean desktop interface.

> ⚠️ **This project is under active development.** Some features may be incomplete or unstable. Contributions and feedback are welcome.

---

## ✨ Features

- 💬 **Text Chat** with Google Search & Code Execution support
- 🖼️ **Image Generation** via Gemini's native image model
- 🤖 **Agentic Pipeline** — an intelligent router that decides when to generate text vs. images
- 👤 **Character & User Profiles** — create and manage personas for conversations
- 📁 **File & Image Uploads** — attach files and images to your messages
- 🔐 **Secure API Key Management** — encrypted local storage with role-based key assignment
- 🖥️ **Desktop App** — runs as a native window via pywebview

---

## 🧩 Modes & Pipelines

### 1. Basic Text — `Enhanced Testing`
The standard text chat mode using Gemini's text model.

- ✅ Supports **Google Search** and **Code Execution** (enable in settings)
- ✅ Supports image/file uploads
- ❌ Does **not** support function-calling features

### 2. Basic Text with Function Calls — `Beta Version`
An experimental text mode with built-in function calling for image generation and image analysis.

- ✅ Supports **Generate Image** and **Image Details** via function calls
- ⚠️ **Do NOT enable** Google Search or Code Execution — they are incompatible with this mode
- 🧪 This mode is in beta and may be unstable

### 3. Image Generation — `Image Version`
Sends your prompt **directly** to Gemini's image generation model with no preprocessing.

- ✅ Best for direct, specific image prompts
- ❌ No text conversation — purely image output
- ❌ No additional features (no search, no code execution)

### 4. Advanced — `Testing / Agentic`
The most capable mode. Uses an intent router to intelligently decide whether your message needs text processing, image generation, or both.

- ✅ Text model **enhances** your prompt before sending to the image model
- ✅ Automatically falls back to text-only mode for regular conversations
- ✅ Give explicit instructions if you want the model to generate images
- ⚠️ Each image generation request uses additional API calls

**Pipeline:**
```
Your Message → Intent Router → Text Model / Image Model → Response / Generated Image → Final Output
```

---

## 🏗️ Architecture

```
RMIX/
├── main.py                  # FastAPI entry point
├── launcher.py              # Desktop app launcher (pywebview)
├── requirements.txt         # Python dependencies
│
├── anchor/                  # Backend logic
│   ├── rp_router.py         # API routes & request routing
│   ├── rp_core.py           # Core utilities (history, profiles, file I/O)
│   ├── rp_lean.py           # Enhanced text pipeline (no function calls)
│   ├── rp_pipe.py           # Beta pipeline (with function calls)
│   ├── logic_router.py      # Agentic intent router
│   ├── img_work.py          # Direct image generation pipeline
│   ├── to_text.py           # Text generation engine
│   ├── to_img.py            # Image generation engine
│   ├── function_executor.py # Function call handler
│   └── secure_config.py     # Encrypted API key management
│
├── frontend/                # React + Vite UI
│   └── src/
│       ├── components/      # Reusable UI components
│       ├── pages/           # Page views
│       ├── services/        # API service layer
│       └── stores/          # Zustand state management
│
├── inst_data/               # System instruction modules
├── function_schema/         # Function call schemas
├── assets/                  # Static assets (avatars, backgrounds)
└── prompts/                 # Prompt templates
```

---

## 🔧 Models Used

| Role | Model |
|---|---|
| Image/File Description | `gemini-3.1-flash-preview` |
| Intent Router | `gemini-3.1-flash-preview` |
| Image Generation | `gemini-3-pro-preview` |
| Text Generation | `gemini-3.1-pro-preview` |

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.10+** — [Download here](https://www.python.org/downloads/)
- **Node.js 18+** — [Download here](https://nodejs.org/) (required for frontend build)
- **Gemini API Key** or **GCP Auth credentials**

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/sysfon009/Artiem.git
   cd Artiem
   ```

2. **Run `RMIX.bat`** — that's it!
   
   The launcher will automatically:
   - Create a Python virtual environment
   - Install all Python dependencies
   - Install npm packages & build the frontend
   - Launch the app in a native desktop window

3. **Set up your API key**
   - Go to **Settings** in the app
   - Add your **Gemini API Key** or **GCP Auth** credentials
   - Assign the key to the appropriate roles

### Launch Options

| Launcher | Mode | Description |
|---|---|---|
| `RMIX.bat` | 🖥️ Desktop Window | Opens in a native window (pywebview). May occasionally have rendering bugs. |
| `beta_launcher.bat` | 🌐 Browser Mode | Runs the server and opens in your browser at `http://127.0.0.1:8000`. Supports auto-reload on code changes. **Recommended for stability.** |

> **💡 Tip:** `beta_launcher.bat` also shows your local IP address, so you can access the app from your phone on the same Wi-Fi network.

---

## ⚠️ Known Limitations

- **System Instructions** for roleplay are not yet editable from the UI. For general-purpose system instructions, use the `inst_work` module in the `inst_data/` directory.
- **Roleplay features** are still under development — full customization and system instruction editing are planned for future updates.
- **Beta mode** (function-calling text) may encounter errors when Google Search or Code Execution are enabled simultaneously.
- **Image generation in Agentic mode** consumes additional API requests per generation cycle.
- Some UI elements and backend connections may still have bugs. If you encounter issues, please open an issue.

> **📝 Note:** You may encounter debug logs and descriptions written in **Indonesian (Bahasa Indonesia)** throughout the codebase and terminal output. These have not been fully translated yet — please disregard them. They do not affect functionality.

---

## 📝 Usage Tips

- **For quick text chats** → Use `Enhanced Testing` with Google Search enabled for up-to-date information.
- **For precise image generation** → Use `Image Version` with direct, specific prompts.
- **For the best overall experience** → Use `Testing / Agentic`. It handles both text and image intelligently, but costs more API calls.
- **For basic text without extra cost** → Use `Enhanced Testing` without any tools enabled.

---

## 📜 License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.  
See the [LICENSE](LICENSE) file for details.

---

## 🤝 Contributing

Contributions are welcome! Feel free to fork, improve, and submit a pull request.  
For major changes, please open an issue first to discuss what you'd like to change.

---

## ❤️ Support

If you find this project useful, any form of support is greatly appreciated. I'm currently unable to test integrations with other LLM providers (such as Claude or GPT) due to limited resources, so contributions in that area — whether code, API credits, or feedback — would be especially meaningful.

*— sysfon, broken mind, to be live.*

---

*Built with [FastAPI](https://fastapi.tiangolo.com/) · [React](https://react.dev/) · [Google Gemini](https://ai.google.dev/) · [pywebview](https://pywebview.flowrl.com/)*
