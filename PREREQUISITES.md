# Prerequisites & Requirements

Everything you need to know before deploying and using this system.

---

## 👥 FOR END USERS (Sales Team)

### Minimum Skills Required
- ✅ No coding knowledge needed
- ✅ No terminal/command line skills needed
- ✅ No software installation needed
- ✅ Can change field values in Airtable
- ✅ Can wait 30-60 seconds for automated results

### What You Need Access To
- Airtable account with **edit access** to "EMD Webseiten" table
- Ability to see the "Kontakt status" field
- Ability to see the "Kontakt error" field (for error details)
- Any modern web browser

### How to Use
1. Open the "EMD Webseiten" table in Airtable
2. Find a record with a domain you want to test
3. Change the "Kontakt status" field to **"to be tested"**
4. Wait 30-60 seconds
5. Check the result:
   - **"passed"** = Website is working correctly
   - **"failed"** = Something broke (see "Kontakt error" field for details)

### No Installation Required
- Everything runs in the cloud (Coolify)
- No software to install on your computer
- No technical setup needed

---

## 👨‍💻 FOR DEVELOPERS/ADMINISTRATORS

### System Requirements (Server)

| Requirement | Details |
|-------------|---------|
| **Operating System** | Linux, Windows, or macOS |
| **Memory (RAM)** | 512 MB minimum, 2 GB recommended |
| **Disk Space** | 1 GB minimum (for screenshots) |
| **Network** | Outbound HTTPS access (ports 443) |
| **Internet Speed** | ≥ 5 Mbps recommended |

### Software Requirements

| Software | Minimum Version | Purpose |
|----------|-----------------|---------|
| **Python** | 3.8+ | Runtime for QA pipeline |
| **pip** | Latest | Package manager |
| **Git** | 2.0+ | Version control |
| **Docker** | 20.0+ | Container (only if deploying with Docker) |
| **Coolify** | (online) | Deployment platform |

### Required External Accounts & Credentials

#### Airtable (REQUIRED)
- **Airtable Personal Access Token** (2 needed)
  - Token 1: For test lead submissions (AIRTABLE_LEADS_API_KEY)
  - Token 2: For trigger + result write-back (AIRTABLE_TRIGGER_API_KEY)
- **How to get:** airtable.com → Account Settings → Developer Hub → Create Token
- **Permissions needed:** Read/Write access to both table bases
- **Sensitivity:** 🔐 KEEP SECRET - don't share or commit to git

#### Google Gemini API (OPTIONAL)
- **Google Gemini API Key**
- **How to get:** aistudio.google.com/apikey
- **Cost:** Free tier available (50 requests/day)
- **Note:** QA pipeline works without this; visual analysis will be skipped
- **Sensitivity:** 🔐 KEEP SECRET

#### Coolify (FOR DEPLOYMENT)
- **Coolify Account**
- **How to get:** coolify.io → Create account
- **Cost:** Free self-hosted or paid managed
- **Permissions:** Admin access to deploy applications

#### GitHub/GitLab (FOR CODE MANAGEMENT)
- **Git Repository**
- **How to get:** github.com or gitlab.com
- **Note:** Must be accessible by Coolify (public or with SSH key)

### Network Requirements

| Connection | Port | Purpose | Direction |
|-----------|------|---------|-----------|
| **Airtable API** | 443 (HTTPS) | Read/write records | Outbound |
| **Google Gemini API** | 443 (HTTPS) | Visual analysis | Outbound |
| **Webhook Endpoint** | 5000 (local) / 443 (Coolify) | Receive QA requests | Inbound |
| **GitHub** | 443 (HTTPS) | Fetch code | Outbound |

---

## 🎯 SKILL REQUIREMENTS BY TASK

### Minimum Skills (Local Testing Only)

**You should be able to:**
- [ ] Navigate a terminal/command line
- [ ] Install Python packages (`pip install`)
- [ ] Generate Airtable API tokens
- [ ] Edit `.env` files
- [ ] Run simple commands (`python script.py`)

**Time to learn:** If new, ~30-60 minutes

### Recommended Skills (Coolify Deployment)

**You should be able to:**
- [ ] All "Minimum" skills above
- [ ] Use Git (`git add`, `git commit`, `git push`)
- [ ] Understand Docker basics (images, containers)
- [ ] Navigate Coolify UI
- [ ] Create and configure Airtable automations
- [ ] Read REST API documentation
- [ ] Understand JSON format

**Time to learn:** If new, ~2-4 hours

### Advanced Skills (Customization)

**You should be able to:**
- [ ] All "Recommended" skills above
- [ ] Python programming (Flask, async/await)
- [ ] Playwright browser automation concepts
- [ ] Docker multi-stage builds
- [ ] Airtable REST API and formulas
- [ ] Debugging Python code
- [ ] Environment variable management

**Time to learn:** If new, ~40+ hours

---

## 🚀 DEPLOYMENT OPTIONS & THEIR REQUIREMENTS

### Option 1: Local Machine (Testing Only)

**Requirements:**
- Python 3.8+
- pip
- Airtable API tokens
- (Optional) Google Gemini API key

**Skills:**
- Terminal basics
- Can follow installation steps

**Cost:** Free (assuming you have a machine)

**Time to setup:** 15-20 minutes

**Limitation:** Your machine must stay on for webhook to work; not suitable for production

**Use case:** Testing before deploying to production

---

### Option 2: Coolify Deployment (Recommended for Production)

**Requirements:**
- Git repository (GitHub/GitLab)
- Coolify account
- Airtable API tokens (2)
- (Optional) Google Gemini API key
- Docker (Coolify handles this automatically)

**Skills:**
- Git basics (`git push`)
- Coolify UI navigation
- Can follow deployment guide
- Airtable automation setup

**Cost:** $5-30/month (depending on server specs)

**Time to setup:** 30-45 minutes (first time)

**Advantage:** Always-on, professional, scalable, no local machine needed

**Use case:** Production deployment

---

### Option 3: Manual VPS Deployment (Advanced)

**Requirements:**
- Linux VPS (DigitalOcean, Linode, etc.)
- SSH access to server
- Python 3.8+ on server
- All API tokens

**Skills:**
- Server administration
- SSH and terminal
- Linux basics
- Can troubleshoot server issues

**Cost:** $5-20/month for VPS

**Time to setup:** 1-2 hours

**Advantage:** Full control, potentially cheaper than Coolify

**Use case:** Organizations with DevOps teams

---

## 📋 PRE-DEPLOYMENT CHECKLIST

Before deploying, you need:

- [ ] Airtable Personal Access Token #1 (AIRTABLE_LEADS_API_KEY)
- [ ] Airtable Personal Access Token #2 (AIRTABLE_TRIGGER_API_KEY)
- [ ] Airtable Base IDs (from URL: airtable.com/appXXXXXXXXXX)
- [ ] Airtable Table Names ("EMD Webseiten", "Leads Partner")
- [ ] Airtable Field Names ("Domain", "Kontakt status", "Kontakt error")
- [ ] (Optional) Google Gemini API Key
- [ ] Git repository with code pushed
- [ ] Coolify account (for production) OR local Python setup (for testing)

---

## 🔐 SECURITY CHECKLIST

**Before going live:**

- [ ] Never commit `.env` file to Git
- [ ] Never hardcode API keys in source code
- [ ] Rotate API tokens if they were ever visible to others
- [ ] Use strong passwords for Airtable/Coolify accounts
- [ ] Use HTTPS for all connections
- [ ] Limit API token permissions to minimum needed
- [ ] Monitor Coolify logs for errors
- [ ] Set up error notifications (optional)

---

## 🆘 TROUBLESHOOTING SKILLS

You might encounter these issues; here's what skill you need to fix them:

| Issue | Skill Needed |
|-------|--------------|
| "Python command not found" | Install Python, add to PATH |
| Webhook doesn't respond | Understand Docker, Coolify logs |
| Airtable integration fails | Airtable API, token generation |
| Form submission test fails | Browser automation basics |
| Gemini analysis shows "SKIPPED" | Google API setup |
| Git authentication fails | Git SSH key setup |

---

## 📚 LEARNING RESOURCES

If you need to learn new skills:

**Git Basics:** https://git-scm.com/docs
**Python:** https://docs.python.org/3/
**Docker:** https://docs.docker.com/
**Airtable API:** https://airtable.com/developers/web/api/introduction
**REST APIs:** https://restfulapi.net/
**Coolify:** https://coolify.io/docs

---

## ✅ READY?

If you have all the requirements above, proceed to:
→ **COOLIFY_DEPLOYMENT.md** for step-by-step deployment instructions

If you're missing something:
→ Use this document to identify what you need before proceeding
