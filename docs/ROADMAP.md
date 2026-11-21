# Digital Operator — Product Plan

## 1. Visi produk

Digital Operator ingin menjadi workspace pribadi yang membantu pengguna mengubah
instruksi menjadi pekerjaan yang tertata, lalu membantu menyelesaikannya melalui
kemampuan yang dapat dipilih dan dikendalikan.

Produk ini tidak dimulai sebagai “AI yang boleh melakukan apa saja”. Kita akan
menambah kemampuan satu per satu, mengukur apakah tiap kemampuan benar-benar
berguna, dan meminta persetujuan sebelum AI melakukan tindakan yang berdampak.

### Pengguna awal

Satu pengguna yang ingin mencatat pekerjaan, mengingat tenggat, dan mengurangi
beban mengatur hal-hal sehari-hari.

### Prinsip produk

1. **Berguna dulu, luas kemudian.** Selesaikan satu alur dengan baik sebelum
   menambah banyak integrasi.
2. **AI mengusulkan; pengguna memutuskan.** Rencana dan tindakan penting harus
   dapat diperiksa dan dikonfirmasi.
3. **Jadwal harus bisa dipercaya.** Waktu, zona waktu, pengiriman, dan status
   pengingat perlu jelas; jangan mengklaim pengingat terkirim jika tidak.
4. **Kemampuan terpisah dan terbatas.** Integrasi hanya mendapat akses yang
   dibutuhkan untuk tugasnya.
5. **Rahasia dan data pengguna dijaga.** Jangan menaruh API key di frontend atau
   mengekspos aplikasi lokal ke internet tanpa kontrol akses.
6. **Setiap fase harus bisa diuji dan dipakai.** Tambahkan tes dan kriteria selesai
   bersama implementasi.

## 2. Kondisi project sekarang

MVP saat ini adalah web app lokal dengan backend FastAPI, SQLite, SQLAlchemy,
dan frontend React/Vite. Pengguna dapat membuat, mengubah, menghapus,
menyelesaikan, dan memfilter tugas, mengelompokkan tugas ke project, menentukan
prioritas, mencari nama/catatan, menambahkan catatan dan waktu, serta melihat
jumlah tugas yang aktif atau terlambat.

Yang sudah ada:

- API `GET`, `POST`, `PATCH`, dan `DELETE` untuk `/api/todos`, pengingat
  persisten, inbox notifikasi, serta worker lokal.
- API CRUD project; todo mendukung project dan prioritas rendah/normal/tinggi.
  UI menyediakan pencarian serta filter project, prioritas, status, dan tenggat.
- Migrasi menambahkan prioritas normal untuk tugas lama; penghapusan project
  mempertahankan tugas dan melepaskan pengelompokannya.
- AI task planner multi-provider dengan alur draft dan konfirmasi.
- Coding-agent MVP untuk mengusulkan perubahan satu file, menampilkan diff,
  lalu menunggu persetujuan sebelum menerapkan.
- Command tetap untuk menjalankan backend tests, dengan konfirmasi terpisah.
- Tes backend, dokumentasi API, dan build frontend.

Yang belum ada:

- Login, multi-user, dan isolasi data.
- Integrasi kalender, email, Telegram, atau layanan eksternal.
- Audit keamanan otomatis yang matang dan deployment untuk penggunaan publik.

**Batas penting MVP:** notifikasi browser saat ini hanya diperiksa ketika
halaman web terbuka. Pemeriksaan dilakukan berkala dan dapat memberi notifikasi
setelah waktu jatuh tempo; ini bukan push notification yang dijamin terkirim.
Coding agent hanya membaca satu file source yang lolos filter best-effort,
mengirimkannya ke provider setelah persetujuan pengguna, dan menunggu review
diff. Project masih untuk penggunaan lokal dan satu pengguna.

## 3. Cara memahami bagian-bagian sistem

Alur web app saat ini:

```text
Pengguna
  -> React/Vite (tampilan dan interaksi)
  -> HTTP API FastAPI (validasi dan aturan aplikasi)
  -> SQLAlchemy (membaca/menulis data)
  -> SQLite (penyimpanan lokal)
```

Komponen berikutnya nanti ditambahkan sebagai alur terpisah:

```text
Instruksi pengguna
  -> AI mengusulkan rencana terstruktur
  -> pengguna memeriksa/mengubah dan menyetujui
  -> backend memvalidasi izin dan menjalankan kemampuan yang diizinkan
  -> hasil dan riwayat ditampilkan
```

### Istilah yang akan sering dipakai

| Istilah | Arti di project |
|---|---|
| **Frontend** | Halaman web React yang dilihat dan digunakan pengguna. |
| **Backend/API** | Layanan FastAPI yang memvalidasi permintaan dan menerapkan aturan. |
| **Database** | Penyimpanan tugas, pengingat, rencana, dan riwayat. |
| **Todo** | Pekerjaan yang ingin dikelola pengguna. |
| **Agent run** | Satu upaya agent memproses instruksi; bukan todo itu sendiri. |
| **Tool** | Kemampuan terbatas, misalnya membuat todo atau mengirim notifikasi. |
| **Provider/LLM** | Layanan/model bahasa yang membantu memahami instruksi. |
| **Scheduler/worker** | Proses background yang menjalankan pekerjaan pada waktu tertentu. |
| **Approval** | Persetujuan eksplisit pengguna sebelum tindakan yang ditentukan. |
| **Migration** | Perubahan skema database yang diterapkan dengan aman ke data lama. |

## 4. Roadmap bertahap

Urutan ini sengaja mengutamakan keandalan sebelum otonomi dan integrasi luas.
Status yang belum dikerjakan tetap **direncanakan**, bukan janji tanggal rilis.

### Rilis produk

Digital Operator memakai semantic versioning: patch memperbaiki bug tanpa
perubahan fitur yang disengaja, minor menambah kemampuan yang kompatibel, dan
major menandai perubahan API/perilaku yang tidak kompatibel. Versi adalah
checkpoint kualitas, bukan klaim bahwa model dasar menyamai Gemini atau OpenAI.
Kualitas agent dibangun lewat konteks yang tepat, tools yang teruji, izin yang
sempit, dan hasil yang dapat diverifikasi.

| Versi | Sasaran | Status |
|---|---|---|
| `0.1.0` | Preview lokal: tugas/pengingat, provider AI, draft, coding proposal yang direview, dan pemeriksaan security lokal. | Fondasi tersedia |
| `0.2.0` | Satu Agent workspace dengan akses konsisten ke tools dan tampilan hasil yang jelas. | UI terpadu, scan lokal, riset publik Gemini, pemeriksaan pasif host berizin, dan audit advisory dependency |
| `0.3.0` | Registry tool tervalidasi; chat dapat mengusulkan pemanggilan tool dan meminta approval sesuai risiko. | Preview: chat dapat mengusulkan riset publik atau scan lokal; eksekusi memerlukan persetujuan pengguna. |
| `0.4.0` | Riwayat agent run, audit tindakan, penanganan kegagalan, batas langkah/waktu, dan pembatalan yang aman. | Direncanakan |
| `0.5.0` | Defensive security lebih dalam untuk repo/lab berizin, termasuk audit dependency dan laporan yang dapat ditindaklanjuti. | Direncanakan |
| `0.6.0` | Integrasi eksternal yang dipilih pengguna dengan izin minimum dan pencabutan akses. | Direncanakan |
| `0.9.0` | Hardening sebelum rilis: auth, isolasi data, migrasi, rate limit, backup, dan deployment terpantau. | Direncanakan |
| `1.0.0` | Rilis stabil setelah kriteria keamanan, reliabilitas, dokumentasi, dan upgrade terpenuhi. | Direncanakan |

Security tooling tetap untuk pertahanan pada project milik pengguna, lingkungan
latihan, atau sistem yang izin pengujiannya telah dipastikan. Tidak ada
kemampuan untuk menyerang target sembarang atau menjalankan aksi destruktif
secara otomatis.

**Arsitektur tujuan:** satu agent mengorkestrasi provider dan registry tool
berizin. Model bahasa adalah komponen yang dapat diganti, bukan satu-satunya
produk; kualitas dan keselamatan harus dibuktikan lewat tes per tool, approval,
audit trail, dan hasil yang bisa diverifikasi.

Riset web publik adalah tool terpisah dan harus dipicu pengguna. Query dikirim
ke Google/Gemini; tool hanya mengembalikan rangkuman dan sumber publik, tidak
mengirim file project atau melakukan tindakan pada situs. Pemeriksaan website
yang tersedia masih pasif: satu HTTPS GET ke path URL pada host allowlist
setelah konfirmasi izin manual; query dan fragment tidak dikirim dan redirect
tidak diikuti. Karena server dapat memberi efek samping pada GET, pengguna harus
memilih path read-only yang diizinkan. Penetration testing tetap berada di luar
kemampuan tool ini dan memerlukan scope serta proses berizin tersendiri.

### Fase 1 — MVP tugas dan pengingat lokal

**Status: selesai sebagai irisan MVP awal.**

- CRUD todo, status selesai, catatan, waktu, filter, dan ringkasan.
- UI web yang berkomunikasi dengan API.
- Tes alur API dan build production frontend.

### Fase 2 — Jadwal dan pengingat yang dapat dipercaya

**Status: implementasi lokal awal selesai; verifikasi dan deployment production
masih perlu dilakukan.**

- `due_at` dan `reminder_at` adalah field terpisah.
- Alembic migration menambahkan kolom pengingat tanpa menghapus todo lama.
- Worker database terpisah memproses reminder yang jatuh tempo dan menyimpan
  notifikasi di inbox.
- Reschedule membuat revisi pengingat baru; menyelesaikan tugas membatalkan
  pengingat yang belum terkirim.
- Web app menampilkan inbox, unread count, dan browser notification opsional.
- Tes mencakup migrasi database baru/lama, pengiriman sekali, filter tugas
  selesai, dan API inbox.

**Batas MVP:** worker lokal menggunakan satu proses terhadap SQLite. Jika worker
berhenti, notifikasi tertunda sampai worker dijalankan kembali. Belum ada kanal
push/email/Telegram, retry delivery provider, autentikasi, atau jaminan
multi-worker untuk deployment terdistribusi.

### Fase 3 — AI sebagai penyusun rencana, bukan pelaksana bebas

**Status: task draft, chat multi-turn, tool proposal dengan approval, riwayat
chat lokal, dan log status aksi dasar tersedia; perlu konfigurasi provider
untuk pemakaian AI nyata.**

- UI menerima instruksi bahasa alami dan menampilkan draft yang bisa diedit.
- UI menyimpan percakapan dan hasil tool di SQLite; pengguna dapat membuka dan
  menghapus riwayat dari sidebar.
- Chat dapat mengusulkan todo, riset publik, atau scan keamanan lokal. Status
  aksi proposal dicatat sebagai menunggu, disetujui/ditolak, selesai, atau gagal.
- Paling banyak 16 pesan terakhir dikirim ke provider untuk tiap respons.
- Adapter OpenAI, Gemini, Anthropic, dan OpenAI-compatible/local.
- Provider default dicoba dulu, lalu provider fallback yang tersedia.
- Backend meminta JSON terstruktur dengan tanggal lokal/timezone dan pertanyaan
  klarifikasi bila perlu.
- Draft AI tidak menulis ke database; todo hanya dibuat dari aksi konfirmasi
  yang terpisah.
- API status provider tidak mengembalikan API keys; tes adapter memakai HTTP
  mock, sehingga tidak memakai token atau koneksi provider sungguhan.

**Batas MVP:** riwayat tersimpan lokal tanpa enkripsi; tidak ada autentikasi,
multi-user isolation, backup otomatis, streaming, registry tool umum,
manajemen API key dari UI, atau credential encryption/secret manager. Log aksi
belum mencakup semua operasi Coding/Security di luar aksi chat. Chat tidak
punya akses shell, browser, atau jaringan umum. Pesan yang dikirim ke provider
dapat berisi data sensitif; perhatikan kebijakan provider. Konfigurasi key dan
model dilakukan melalui `.env` backend.

### Fase 4 — Fondasi agent dan kontrol tindakan

**Status: coding-agent MVP terbatas dan pemeriksaan security statis lokal tersedia;
fondasi agent penuh masih direncanakan.**

- Coding agent mengusulkan perubahan satu file eligible dan menyimpan proposal
  untuk review; tidak menerapkan perubahan sebelum approval eksplisit.
- Approval memeriksa hash sumber agar proposal lama tidak menimpa perubahan
  terbaru.
- File tersembunyi, environment, dependency/build, dan file yang cocok dengan
  pola credential tidak ditawarkan. Filter ini best-effort, bukan jaminan
  deteksi semua rahasia.
- Hanya command backend test tetap yang tersedia dan setiap eksekusi memerlukan
  persetujuan tersendiri.
- Halaman Security menjalankan pemeriksaan pola source/config, termasuk AST
  untuk beberapa risiko Python dan dukungan konfigurasi multiline; tidak
  mengeksekusi kode, mengakses jaringan, atau mengirim source ke provider.
- Hasil pemeriksaan statis adalah petunjuk untuk review manual, bukan bukti
  kerentanan atau jaminan keamanan.
- Belum ada registry tool umum, agent run lengkap, audit trail menyeluruh,
  pembatalan, atau autentikasi.

**Kriteria selesai:** agent hanya dapat memakai tool yang terdaftar, input
divalidasi backend, dan tindakan berisiko memerlukan persetujuan.

### Fase 5 — Satu integrasi yang dipilih pengguna

- Pilih satu kanal/integrasi berdasarkan kebiasaan nyata: misalnya Telegram
  untuk notifikasi atau kalender untuk sinkronisasi jadwal.
- Tentukan izin minimum, cara menyimpan/mencabut kredensial, dan cara mengatasi
  token kedaluwarsa sebelum implementasi.
- Tambahkan tes integrasi tanpa bergantung pada akun pribadi.

**Kriteria selesai:** pengguna dapat menghubungkan, menguji, dan memutus
integrasi tanpa mengekspos rahasia atau membuat aksi duplikat.

### Fase 6 — Keamanan dan kesiapan deployment

Kerjakan sebelum layanan dibuka ke jaringan publik atau digunakan banyak orang:

- Autentikasi dan otorisasi; semua data harus terikat pada pemiliknya.
- Simpan rahasia di konfigurasi server/secret manager, bukan kode atau frontend.
- Gunakan database production dan migration yang teruji; sediakan backup serta
  prosedur pemulihan.
- Batasi request, validasi input, log tanpa rahasia, dan pantau error/health.
- Atur HTTPS, origin CORS, kebijakan penyimpanan data, serta cara menghapus data.
- Tinjau risiko prompt injection dan konten tak tepercaya sebelum agent membaca
  halaman, email, atau dokumen.

### Fase 7 — Perluasan produk berdasarkan penggunaan

Setelah fase sebelumnya stabil, evaluasi fitur seperti proyek dan prioritas,
pencarian, ringkasan harian, input suara, dokumen, aplikasi mobile, workspace
bersama, atau integrasi lain. Urutannya ditentukan oleh feedback dan metrik,
bukan sekadar banyaknya fitur.

## 5. Rencana kerja paling dekat

Sebelum memperluas kemampuan, urutan implementasi berikut direkomendasikan:

1. **Organisasi kerja:** tambahkan project, prioritas, pencarian, dan filter
   tugas agar workspace berguna untuk pekerjaan harian.
2. **Validasi alur UI:** uji riwayat chat, transisi approval aksi, coding
   proposal, review diff, reject/approve, dan deteksi file stale.
3. **Konteks project read-only:** bantu agent menemukan source relevan secara
   lokal tanpa eksekusi kode; perubahan tetap berupa proposal yang direview.
4. **Coba provider sungguhan dengan source non-sensitif:** pastikan consent,
   biaya, fallback, serta penanganan error dipahami sebelum dipakai rutin.
5. **Tingkatkan pemeriksaan defensif repo ini:** validasi temuan heuristik dan
   rancang pemeriksaan dependency dengan sumber advisori yang tepercaya.
6. **Analisis website dengan izin:** tentukan domain yang dimiliki/diizinkan dan
   batasi analisis awal ke halaman read-only sebelum menambah kemampuan lain.
7. **Kesiapan deployment:** backup/restore, authentication, authorization,
   pembatasan jaringan, dan isolasi data harus selesai sebelum akses multi-user.

Ini menjaga ruang lingkup tetap kecil: belum ada akses email, browser agent,
pembelian, pengiriman pesan otomatis, atau tindakan lain atas nama pengguna.

## 6. Cara kerja dan ukuran keberhasilan

Untuk setiap fitur:

1. Sepakati masalah pengguna dan skenario berhasil.
2. Tentukan perilaku gagal dan batas izin.
3. Implementasikan perubahan backend, UI, dan dokumentasinya bersama.
4. Tambahkan tes API/unit; tambahkan tes browser untuk alur pengguna penting.
5. Jalankan suite yang relevan dan periksa hasilnya sebelum lanjut.
6. Catat perubahan status roadmap setelah implementasi benar-benar selesai.

Metrik awal yang lebih berguna daripada jumlah fitur:

- Berapa banyak draft AI yang diterima atau diedit sebelum disimpan.
- Berapa banyak pengingat yang gagal, terlambat, atau terkirim ganda.
- Apakah pengguna kembali menggunakan alur tugas setiap minggu.
- Apakah setiap tindakan agent dapat dijelaskan dan dibatalkan/diperbaiki.

## 7. Keputusan yang perlu dibuat bersama

Sebelum memilih integrasi atau membuka akses aplikasi, sepakati:

- Apakah pengingat MVP pertama harus hanya muncul di aplikasi, atau juga
  dikirim melalui Telegram/email?
- Model/provider AI mana yang diinginkan dan berapa batas biaya yang nyaman?
- Apakah project akan tetap untuk penggunaan pribadi, atau memang akan
  dibuka untuk banyak pengguna?

Sampai keputusan itu dibuat, asumsi aman adalah penggunaan pribadi lokal,
pengingat internal dulu, dan AI hanya membuat draft yang menunggu konfirmasi.
