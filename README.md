# LinkedIn Auto-Poster

This project automatically scrapes content from specified URLs (including Google Docs/Wiki links), summarizes them using Gemini AI, and posts the results to LinkedIn with appropriate formatting (Unicode bold, emojis, hashtags).

## Features

- **Web Scraping**: Extracts content and images from URLs.
- **Google Docs Integration**: Specifically handles `tony.banya.ai/wiki` links by fetching the Google Doc HTML export.
- **AI Summarization**: Uses Gemini AI to create professional LinkedIn posts.
- **Multi-language Support**: Handles English and Korean content separately based on `contents.json`.
- **LinkedIn Integration**: Posts text and images to LinkedIn profiles.
- **Unicode Bold**: Uses special characters for emphasis since LinkedIn doesn't support Markdown.

## Setup

1. **Virtual Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Environment Variables**:
   Create a `.env` file with the following keys:
   - `LINKEDIN_CLIENT_ID`
   - `LINKEDIN_CLIENT_SECRET`
   - `LINKEDIN_REDIRECT_URI`
   - `LINKEDIN_ACCESS_TOKEN`
   - `LINKEDIN_PERSON_URN`
   - `GEMINI_API_KEY`

3. **Content Configuration**:
   Update `contents.json` with the URLs you want to post.

## Usage

Run the main script:
```bash
python main.py
```

## License

MIT

