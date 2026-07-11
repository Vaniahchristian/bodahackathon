"""Launch Ekkubo Gradio app — use as the main cell in a Kaggle notebook."""

from ekkubo.app import build_app

if __name__ == "__main__":
    # Kaggle: add GEMINI_API_KEY via Add-ons → Secrets
    app = build_app()
    app.launch(server_name="0.0.0.0", server_port=7860, share=False)
