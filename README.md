# DAIN — DUNITE Achievement & Impact Network

> **Official PR & Media Amplification Platform for the Dhaka University Ecosystem**

![DAIN Banner](assets/dunite-logo.png)

DAIN systematically identifies, documents, verifies, and amplifies the achievements, innovations, research breakthroughs, and impact stories originating from Dhaka University students, alumni, and faculty members across 100+ national and international media outlets.

---

## 🌟 Key Features

1. **5 Core Achievement Sectors**:
   - 🎓 **Academic & Research**: Scholarships, high-impact journal publications, conference awards, international admissions, fellowships.
   - 💼 **Professional & Corporate**: Promotions, leadership appointments at Fortune 500s/MNCs, industry certifications.
   - 🚀 **Entrepreneurship & Startups**: Venture launches, VC/Angel funding announcements, global accelerator selections.
   - 🌍 **Social Impact & Community**: Volunteer initiatives, public policy contributions, NGO campaigns.
   - ⭐ **Personal Milestones**: Inspiring journeys, career breakthroughs, human interest stories.

2. **3-Stage Content Review & Verification Pipeline**:
   - **Stage 01: Automated Validation**: Completeness check, `@du.ac.bd` domain auto-verification, duplicate detection.
   - **Stage 02: Editorial Review**: Fact verification, newsworthiness check, media kit narrative polish.
   - **Stage 03: Publication & Media Routing**: Concentric syndication to 100+ partner newsrooms.

3. **Exploded Press Kit Deconstructor**:
   - Generates 5 media-ready layers: *Headline & Lead*, *Executive Summary for Press*, *Detailed Story Narrative*, *Proof & Verification Vault*, *Verified Contact Information*.

4. **100+ Media Distribution Network**:
   - 4-Tier concentric routing across National TV/Dailies, Digital Tech/Business portals, University Channels, and Byte-Sized Social Syndication.

---

## 🚀 Live Demo & Deployment

This is an **ultra-lightweight static web application (0 MB `node_modules`)** styled with the **Google Stitch Dark Theme** and **Tailwind CSS**.

### 1. Deploying to Vercel (Instant 1-Click)
- Import this GitHub repository into [Vercel](https://vercel.com).
- **Framework Preset**: `Other`
- **Build Command**: *(leave empty)*
- **Output Directory**: `.` *(current directory)*
- **Environment Variables**: No frontend secrets. Configure the public API URL in `index.html` and deploy the backend as described in [DEPLOY.md](DEPLOY.md).

### 2. Deploying to Netlify
- Import this GitHub repository into [Netlify](https://netlify.com).
- **Publish directory**: `.` *(root)*
- **Build command**: *(leave empty)*

### 3. Deploying to GitHub Pages
- Go to repository **Settings** &rarr; **Pages**.
- Source: **Deploy from a branch** &rarr; Branch: `main` &rarr; Folder: `/ (root)`.

---

## 💻 Local Execution

To run locally on your machine without installing any dependencies:
1. Double-click `Launch_DAIN_Platform.bat`, or run:
```bash
python -m http.server 3000
```
2. Open `http://localhost:3000` in any web browser.

---

## Environment setup

The backend template is [backend/.env.example](backend/.env.example). Configure
production values in the host dashboard as described in [DEPLOY.md](DEPLOY.md);
never commit local environment files or real keys. The template uses production
safety settings; local development instructions are in [backend/README.md](backend/README.md).
The static frontend's public API URL is configured in the root `api-config.js` file
with `window.DAIN_API_BASE`; host environment variables are not automatically
substituted into static files. Set it to the public backend origin (without `/docs`,
`/health`, or API paths). Keep all provider/database secrets on the backend only.

## 🏛️ Brand & Governance

Built under the **DUNITE Governance Framework** for Dhaka University.
- **Color Palette**: `surface-navy` (`#000A1E`), `dunite-red` (`#BE0000`), `academic-gold` (`#FED488`).
- **Typography**: `Public Sans`, `Inter`, `JetBrains Mono`.
