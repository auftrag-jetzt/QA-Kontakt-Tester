# Coolify Deployment & Airtable Automation Setup

Complete step-by-step guide to deploy the webhook server on Coolify and configure Airtable automation.

---

## PART 1: PREPARE YOUR GIT REPOSITORY

### Step 1: Commit your code to Git

```bash
cd /Users/hrs978/Downloads/old\ downloads/work/test\ cluade\ API
git add .
git commit -m "Add webhook server with error field tracking"
git push origin main
```

If you don't have a remote (GitHub/GitLab), create one:
1. Go to GitHub → New Repository
2. Copy the HTTPS URL
3. Run: `git remote add origin https://github.com/yourname/your-repo.git`
4. Then push: `git push -u origin main`

---

## PART 2: DEPLOY TO COOLIFY

### Step 1: Access Coolify Dashboard

- Go to your Coolify instance (e.g., `https://coolify.your-domain.com`)
- Login to your account

### Step 2: Create New Application

1. Click **Applications** → **New Application**
2. Choose **Docker** as build method
3. Paste your Git repository URL (HTTPS, e.g., `https://github.com/yourname/your-repo.git`)

### Step 3: Configure Build Settings

- **Build context:** `webhook-server` (the folder with `Dockerfile`)
- **Dockerfile location:** `webhook-server/Dockerfile`
- **Branch:** `main`

### Step 4: Add Environment Variables

In Coolify UI, go to **Settings** → **Environment Variables** and add:

```
AIRTABLE_LEADS_API_KEY=patgO7RT4vcjoIngN.d350f920f7123b090f193639372bc97ad89b5ce475dae77cf8d2075d9da3e642
AIRTABLE_LEADS_BASE_ID=appL4PpAWoTl3rEzE
AIRTABLE_LEADS_TABLE=Leads Partner

AIRTABLE_TRIGGER_API_KEY=patUqrGwBoazZinsv.557710fd500160eb3fd64ed6eb6330808b8c046d098c0f3aad43c55fff6cfbe1
AIRTABLE_TRIGGER_BASE_ID=apphwncsSpj5PTIFX
AIRTABLE_TRIGGER_TABLE=EMD Webseiten
AIRTABLE_TRIGGER_DOMAIN_FIELD=Domain
AIRTABLE_TRIGGER_RESULT_FIELD=Kontakt status
AIRTABLE_TRIGGER_ERROR_FIELD=Kontakt error

GEMINI_API_KEY=  (optional, leave blank if not using)
```

### Step 5: Deploy

1. Click **Deploy** button
2. Wait 3-5 minutes for Docker build
3. Once deployed, Coolify will show you the public URL: **`https://your-app-name.coolify.io`**

### Step 6: Test the webhook

```bash
curl -X POST https://your-app-name.coolify.io/run-qa \
  -H "Content-Type: application/json" \
  -d '{"domain": "example.de", "record_id": "recXXXXXXXXXXXXXX"}'
```

You should get a response like:
```json
{
  "status": "PASS",
  "message": "QA run completed",
  "airtable_record_id": "recXXXXXXXXXXXXXX",
  "details": {...}
}
```

✅ **If you got a response, your webhook is live!**

---

## PART 3: CONFIGURE AIRTABLE AUTOMATION

### In the "EMD Webseiten" base:

#### Step 1: Create Automation

1. Go to **Automations** tab
2. Click **Create Automation**

#### Step 2: Set Up Trigger

1. Choose trigger: **"When a record matches conditions"**
2. Set condition:
   - **Field:** `Kontakt status`
   - **Condition:** `is equal to`
   - **Value:** `to be tested`

   This means: "When someone changes the Kontakt status field to 'to be tested', trigger the automation"

#### Step 3: Add Action 1 — Lock the Record

1. Click **+ Add action**
2. Action type: **Update record**
3. Configure:
   - **Field:** `Kontakt status`
   - **Value:** `testing`
   
   This prevents duplicate triggers while the QA runs.

#### Step 4: Add Action 2 — Call the Webhook

1. Click **+ Add action**
2. Action type: **Send a webhook**
3. Configure:
   - **Method:** `POST`
   - **URL:** `https://your-app-name.coolify.io/run-qa`
   - **Headers:**
     ```
     Content-Type: application/json
     ```
   - **Body (raw JSON):**
     ```json
     {
       "record_id": {record_id},
       "domain": {Domain}
     }
     ```
     
   ⚠️ **Important:** In Airtable automation, `{record_id}` and `{Domain}` are special placeholders that auto-substitute the values from the record.

#### Step 5: Save Automation

1. Give it a name: e.g., "QA Test Webhook"
2. Click **Save**

---

## PART 4: HOW IT WORKS

```
Sales employee sets Kontakt status → "to be tested"
         ↓
Airtable Automation triggers:
  1. Sets Kontakt status → "testing" (locks record)
  2. Sends POST to /run-qa with { "record_id": "...", "domain": "..." }
         ↓
Webhook server receives request:
  1. Calls set_status_to_testing() [already done in automation, but safe redundant]
  2. Calls run_domain(domain, airtable_record_id)
         ↓
QA Pipeline runs:
  1. Takes screenshot
  2. Analyzes with Gemini (if API key present)
  3. Tests contact form submission
  4. Checks Airtable integration (B1/B2/C)
         ↓
Results written back to Airtable record:
  - Kontakt status → "passed" or "failed"
  - Kontakt error → error details (if any failure)
         ↓
Sales employee sees result immediately
```

---

## TESTING CHECKLIST

- [ ] Coolify deployment complete (app is running)
- [ ] Environment variables set in Coolify
- [ ] Webhook responds to test curl request
- [ ] Airtable automation created & saved
- [ ] Test run:
  1. Find a test record in EMD Webseiten table
  2. Change "Kontakt status" to "to be tested"
  3. Wait 30-60 seconds
  4. Verify "Kontakt status" changed to "passed" or "failed"
  5. Check "Kontakt error" field for any error messages
- [ ] Test with multiple domains to ensure scalability

---

## TROUBLESHOOTING

### Webhook doesn't respond (404 or timeout)
- Verify the Coolify app is running (green status in Coolify UI)
- Check environment variables are set
- Verify the URL is correct

### Airtable automation doesn't fire
- Check "Kontakt status" field values are exactly: `untested`, `to be tested`, `testing`, `passed`, `failed`
- Verify automation is enabled (should show checkmark)
- Test by manually changing the field to "to be tested"

### Result not written back to Airtable
- Verify `AIRTABLE_TRIGGER_API_KEY` and `AIRTABLE_TRIGGER_BASE_ID` are set in Coolify
- Check Coolify logs for errors (Settings → Logs)
- Verify the API key has permissions to write to the table

### "Kontakt error" field is empty
- The field only gets populated if there's an actual error
- If QA passed (no errors), the field will be blank
- Check "Kontakt status" to see the final result

---

## SECURITY NOTES

⚠️ **API Keys in .env:**
- The `.env` file contains real API keys
- **NEVER commit `.env` to git** (should be in `.gitignore`)
- Coolify stores secrets separately in its environment variable vault
- If you accidentally commit secrets, rotate the tokens immediately

---

## NEXT STEPS

1. Deploy to Coolify (follow Part 2)
2. Configure Airtable automation (follow Part 3)
3. Test with a single record (follow Testing Checklist)
4. Monitor Coolify logs for any errors
5. Celebrate! 🎉
