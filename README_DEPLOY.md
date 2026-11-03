# สอน deploy ฟรี (Web app — ใช้ได้ทุกอุปกรณ์)

เป้าหมาย: ตัวเว็บแอปอยู่ที่ GitHub Pages (ฟรี), backend อยู่ที่ Render (ฟรี),
ฐานข้อมูล PostgreSQL (ฟรี) — ทั้งหมดไม่ต้องผูกบัตร ใช้ผ่านมือถือได้ทุกที่ HTTPS อัตโนมัติ

```
มือถือ/แท็บ/PC ──https──▶ GitHub Pages (UI หน้าเว็บ)
                              │
                              └──https──▶ Render (FastAPI backend)
                                              │
                                              └──▶ PostgreSQL (Supabase หรือ Render DB)
```

---

## 0. ของที่ต้องมีก่อน

- GitHub account (มีอยู่แล้ว — repo นี้)
- Render account → https://render.com สมัครฟรี (ไม่ต้องผูกบัตร)
- GROQ API key (ที่ใช้อยู่แล้วใน `.env`)

---

## 1. สร้างฐานข้อมูล PostgreSQL (เลือกอย่างใดอย่างหนึ่ง)

### ทาง A — Supabase (แนะนำ, ฟรีถาวร 500MB)
1. ไป https://supabase.com → New project (ฟรี ไม่ต้องผูกบัตร)
2. ตั้งชื่อ + region (เลือก Southeast Asia/Singapore → ใกล้ไทย)
3. หลังสร้างเสร็จ: **Project Settings → Database → Connection string → URI**
4. คัดลอกลิงก์ `postgresql://postgres.xxxx:xxxx@aws-0-...pooler.supabase.com:5432/postgres`
   แล้วต่อท้าย `?sslmode=require`
   → เก็บไว้สำหรับ step 2.3

### ทาง B — Render built-in Postgres (ง่ายสุด แต่ฟรีหมดอายุ 30 วัน)
ถ้าทำทาง A แล้วข้ามไปได้เลย (A ฟรีถาวรกว่า)
ถ้าใช้ render.yaml blueprint ข้างล่าง Render จะสร้าง DB ให้เองอัตโนมัติ

> ⚠️ **Render Postgres ฟรีหมดอายุ 30 วัน** — วางแผนย้ายไป Supabase (ทาง A) ก่อนหมดอายุ
> ข้อมูลจะยังอยู่ที่ Render DB หลังหมดอายุ? ไม่ — หายถ้าไม่ backup — ให้ migrate ก่อน (ด้านล่าง)

### ย้ายข้อมูลจาก Render Postgres → Supabase (ทำตอนใกล้หมดอายุ)
เครื่องที่ติดตั้ง `pg_dump`/`psql` ไว้ (หรือใช้ Render Dashboard → Database → **Shell**):

```powershell
# 1) dump DB เดิม (ใช้ External Database URL ของ Render — ดูหน้า Database)
pg_dump "postgresql://<user>:<pass>@<host>:5432/<db>" --clean --if-exists --format=plain > backup.sql

# 2) ใส่เข้าถึง Supabase (URI จากทาง A ข้อ 4)
$env:PGPASSWORD = "<supabase-password>"
psql "postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres" -f backup.sql
```

ถ้าไม่อยากลากข้อมูลเก่า (ยอมเริ่มใหม่): ข้าม 2 ขั้นนี้ได้เลย — สลับ `DATABASE_URL` แล้วแอปจะสร้างตารางใหม่ให้เอง (`create_all` ตอน start)

แล้วสลับที่ Render Service → **Environment** → แก้ `DATABASE_URL` เป็น URI ของ Supabase (ต่อท้าย `?sslmode=require`) → **Save** (deploy ใหม่) → เปิด `https://<api-url>/settings/holidays` ควรคืน `{"enabled":true}`

---

## 2. Deploy backend ขึ้น Render

### วิธีที่ 1 — Blueprint (ง่ายสุด ถ้าใช้ render.yaml)
1. Render Dashboard → **New → Blueprint**
2. เลือก repo นี้ (ต้อง push โค้ดขึ้น GitHub ก่อน)
3. Render จะเห็น `render.yaml` → กด Apply
4. หลัง deploy เสร็จ ไปที่ Service → **Environment** แล้วตั้ง:
   - `GROQ_API_KEY` = คีย์ของคุณ
   - `ALLOWED_ORIGINS` = `https://whyohkay.github.io` (origin ของหน้าเว็บ — ไม่ลงท้าย `/` ไม่มีชื่อ repo ต่อท้าย เพราะ CORS ดูแค่ domain)   
   - (ถ้าต้องการ DB แบบ Supabase ให้แก้ `DATABASE_URL` แทนค่าอัตโนมัติ)
5. กด Save → deploy ใหม่
6. ดู URL ของ API ได้ที่หน้า Service (URL ปัจจุบันคือ `https://smart-task-manager-api-1ldk.onrender.com` — ดูจากหน้า Service เองเสมอ เปลี่ยนทุกครั้งที่ deploy ใหม่)
7. ทดสอบ: เปิด `https://<api-url>/` ควรเห็น JSON `{"message": "Hello Smart Task Manager"}`

### วิธีที่ 2 — ตั้งมือ
1. Render → **New → Web Service**
2. Connect GitHub repo → ตั้ง:
   - **Runtime**: Docker
   - **Root Directory**: `smart-task-manager`
   - **Region**: Singapore
3. ข้างล่าง **Environment Variables** เพิ่ม (4 ตัว):
   | key | value |
   |---|---|
   | `DATABASE_URL` | ลิงก์จาก step 1 |
   | `GROQ_API_KEY` | คีย์ Groq |
   | `ALLOWED_ORIGINS` | `https://<username>.github.io` |
   | `BACKGROUND_WORKER` | `1` |
4. Create Web Service → รอ build/deploy (~2-5 นาที)
5. ทดสอบ `https://<api-url>/` เหมือนวิธีที่ 1

> **หมายเหตุ 1 — create_all:** แอปสร้างตารางทั้งหมดเองตอน start (DB ใหม่ไม่ต้องรัน alembic)
>
> **หมายเหตุ 2 — free tier หลับ:** Render ฟรีจะหลับถ้าไม่มีใครเรียก 15 นาที → กดเข้าเว็บครั้งแรกช้าหน่อย (cold start ~30-60 วินาที) และตอนหลับ background worker ก็ไม่วิ่ง (push จะส่งได้เฉพาะตอนแอปตื่น) — อยากให้ตื่นตลอด ใช้ UptimeRobot ฟรี ping `https://<api-url>/` ทุก 5 นาที
>
> **หมายเหตุ 3 — ตัวแปรใน render.yaml:** `sync: false` = ตั้งค่าตอน deploy เอง ไม่ commit ลงไฟล์ (กัน GROQ_API_KEY รั่วลง git)

---

## 3. Deploy หน้าเว็บ (Flutter web) — repo public แยก (เพราะ repo ต้นทางเป็น private)

> **ทำไมต้อง repo แยก:** GitHub Pages ฟรีเฉพาะ repo **public** — repo ต้นทาง (`stm`) ของคุณเป็น private
> เลยต้องมี repo public อีกตัวไว้เก็บหน้าเว็บ (เช่น `stm-web`) โดย source code ยังอยู่ใน repo ส่วนตัวเหมือนเดิม
> GitHub Actions จะ build แล้ว push `build/web` ไปให้อัตโนมัติ

### 3.1 สร้าง repo public ไว้เก็บหน้าเว็บ
1. GitHub → **New repository**
   - Repository name: `stm-web` (ต้องตรงเป๊ะ หรือแก้ตัวแปร `WEB_REPO` ใน workflow — ดูด้านล่าง)
   - **Public** (บังคับ — ไม่งั้น Pages เสียตังอีก)
   - ไม่ต้องติ๊ก Add README (จะ push ทับ)
2. ไปที่ repo `stm-web` → **Settings → Pages** → Source: **Deploy from a branch** → `main` / root → Save

### 3.2 สร้าง deploy key (ให้ GitHub Actions ของ repo ส่วนตัว เขียนไฟล์ไป repo public ได้)
รันใน PowerShell (เครื่องคุณ):

```powershell
ssh-keygen -t ed25519 -C "stm-web-deploy" -f "$env:USERPROFILE\.ssh\stm_web_deploy" -N ""
Get-Content "$env:USERPROFILE\.ssh\stm_web_deploy.pub"
```

1. คัดลอกผลลัพธ์ (public key `ssh-ed25519 ...`) → ไป repo **`stm-web`** → **Settings → Deploy keys → Add deploy key**:
   - Title: `stm-web-deploy`
   - Key: วาง public key
   - **Allow write access** ← ต้องติ๊ก ไม่งั้น push ไม่ได้
2. เอา private key ไปใส่เป็น secret ของ repo ต้นทาง **`stm`** → **Settings → Secrets and variables → Actions → New secret**:
   - Name: `STM_WEB_DEPLOY_KEY`
   - Value: วางเนื้อไฟล์ `stm_web_deploy` **ทั้งไฟล์** (เริ่มจาก `-----BEGIN OPENSSH PRIVATE KEY-----` ถึง `-----END OPENSSH PRIVATE KEY-----`)

### 3.3 ตั้ง API_BASE (ตัวแปรของ repo `stm`)
repo **`stm`** → **Settings → Secrets and variables → Actions → Variables → New repository variable**:
- Name: `API_BASE` / Value: URL backend ปัจจุบัน เช่น `https://smart-task-manager-api-1ldk.onrender.com` (**ไม่ลงท้าย `/`** — ดูจากหน้า Render Service เสมอ เพราะ URL เปลี่ยนได้ทุก deploy)

### 3.4 build + push ขึ้นเว็บ
- การตั้งค่าทั้งหมดเสร็จแล้ว **push อะไรก็ได้ขึ้น `main`** → GitHub Actions จะ build web แล้ว push หน้าเว็บไป `stm-web` อัตโนมัติ
- ถ้า push ไปแล้วรอบนึงก่อนตั้งค่าเสร็จ → ไป **Actions** tab → กด **Re-run jobs** อีกรอบ
- เปิดผลลัพธ์ที่ `https://whyohkay.github.io/stm-web/`

> อยากเปลี่ยนชื่อ repo/owner หน้าเว็บ? ตั้ง repo variables 2 ตัวใน repo `stm` ได้เลย (ไม่ต้องแก้ไฟล์):
> `WEB_REPO` = ชื่อ repo (default `stm-web`), `WEB_OWNER` = ชื่อบัญชี (default `whyohkay`)
>
> ทดสอบ build ในเครื่องเองก็ได้ (ไม่ใช้ Actions):
> ```powershell
> cd smart_task_app
> flutter build web --release --base-href=/stm-web/ --dart-define=API_BASE=https://<api-url>
> ```
> แล้วอัปโหลดเนื้อ `build\web` ขึ้น `stm-web` ด้วยตนเอง (ลากวางใน GitHub web UI ก็ได้)

---

## 4. ตั้งค่าในแอป (ครั้งเดียว หลังทุกอย่างขึ้น)

- เปิดแอป → **Settings** (เกียร์) → **Push Notification** → เปิดสวิตช์
- เปิดหน้าแรกจะถามสิทธิ์แจ้งเตือนจากเบราว์เซอร์ → อนุญาต
- สร้างงานที่มี deadline ใกล้ ๆ → รอ worker ส่ง push (ต้องมี `BACKGROUND_WORKER=1` และแอปไม่หลับ)

---

## 5. ใช้ในอุปกรณ์อื่น

- **มือถือ/แท็บ/เครื่องอื่น**: เปิด `https://whyohkay.github.io/stm-web/` ในเบราว์เซอร์
  (Chrome ดีที่สุด เพราะ push/subscribe + file picker รองรับดีสุด) → เพิ่มไปหน้าแรกได้
- ทุกอุปกรณ์ใช้ database ตัวเดียวกัน (แชร์งาน/พลังงาน/แต้มร่วมกัน)

---

## 6. Native app (Android/iOS) — push ผ่าน Firebase (FCM)

> Web ใช้ Web Push VAPID (ไม่ต้อง Firebase) — ถึง step นี้เฉพาะตอนอยากได้แอป native
> โค้ด frontend (`push_integration.dart`) + backend (`push_service.py` FCM v1) เตรียมไว้แล้ว
> เหลือแค่ตั้งค่า Firebase project + สร้างแอป native

### 6.1 สร้าง Firebase project + ลงทะเบียนแอป
1. https://console.firebase.google.com → **Add project**
2. **Add app → Android**: ใส่ package id = `com.example.smart_task_app` (ตรงกับ `android/app/build.gradle.kts`)
   → ดาวน์โหลด `google-services.json` ไปวางที่ `smart_task_app/android/app/google-services.json`
3. **Add app → iOS**: ใส่ bundle id = `com.example.smartTaskApp` (ดูจาก `ios/Runner.xcodeproj` จริง — ถ้ายังไม่ตั้งให้แก้ `ios/Runner.xcscheme`/Info.plist ให้ตรง)
   → ดาวน์โหลด `GoogleService-Info.plist` ไปวางที่ `smart_task_app/ios/Runner/GoogleService-Info.plist`
4. โครงการ Firebase → **Project settings → Service accounts → Generate new private key** → ได้ไฟล์ JSON (service account) → เก็บไว้ (step 6.3)

### 6.2 iOS: เปิด Push capability
- เปิด `ios/Runner.xcworkspace` ใน Xcode → Signing & Capabilities → **+ Push Notifications** + **+ Background Modes → Remote notifications**
- (ต้องมี Apple Developer account — ฟรีทีหลังต้องผูกทีม)

### 6.3 ตั้ง env บน Render (ส่ง push ไป native)
เพิ่ม env variable บน Service (Render) — เป็น **path ไฟล์** หรือวาง **JSON string ทั้งก้อน** ก็ได้:
| key | value |
|---|---|
| `FIREBASE_SERVICE_ACCOUNT` | เนื้อไฟล์ service account JSON (จาก 6.1 ข้อ 4) หรือ path |

ไม่ตั้ง env นี้ = แอป native ยังเปิดได้ปกติ แต่สวิตช์ push เปิดไม่ได้ (backend ข้าม native device เงียบ ๆ)

### 6.4 Build & ตรวจ
```powershell
cd smart_task_app
flutter build apk --dart-define=API_BASE=https://<api-url>
flutter run -d <device> --dart-define=API_BASE=https://<api-url>
```
- เปิดสวิตช์ Push ใน Settings → อนุญาต → แอปส่ง FCM token ไป `POST /devices` (platform=android/ios)
- สร้างงานด่วน → backend ส่ง FCM v1 ผ่าน `firebase-admin` (ต้องติดตั้งอยู่แล้วใน `requirements.txt`)
- token หมดอายุ (ผู้ใช้ถอนสิทธิ์) → backend ลบ device ทิ้งให้เอง (ไม่ spam)

> **หมายเหตุ:** ตอนนี้มีเฉพาะ `flutter run -d chrome` (web) — build native ครั้งแรกต้องติดตั้ง
> Android SDK / Xcode ตาม Flutter setup ปกติก่อน และมีไฟล์ config จาก 6.1 ครบ

---

## Troubleshooting

| อาการ | สาเหตุ/แก้ |
|---|---|
| หน้าเว็บขาว | ลืม `--base-href` หรือ API_BASE ผิด → rebuild |
| API เรียกไม่ได้ (CORS) | `ALLOWED_ORIGINS` ไม่ตรง origin ของหน้าเว็บ (ต้องเป็น `https://<user>.github.io` ไม่ลงท้าย `/`) |
| push ไม่เด้ง | free tier หลับ (ดูหมายเหตุ 2); สวิตช์ใน Settings ยังปิด; ยังไม่กดอนุญาต |
| subscription ตายหลัง deploy | ลบ device ใน DB หรือกดปิด/เปิดสวิตช์ใหม่ใน Settings |
| `a.synchronize` / schema error | DB เก่าจาก local → ใช้ DB ใหม่บนคลาวด์แทน ไม่ได้เอา local DB มา |
