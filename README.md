Ya, bisa! Anda bisa menambahkan tombol atau lencana (badge) donasi di file `README.md`. Caranya adalah dengan menggunakan format gambar yang bisa diklik (link).

Saya sudah menambahkan tombol donasi yang menarik menggunakan **Shields.io** (standar industri untuk badge GitHub) tepat di bawah judul.

Berikut adalah file **`README.md`** yang sudah diperbarui dengan tombol donasi:

```markdown
# NS MetaRefiner

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![License](https://img.shields.io/badge/license-Free-green)

<!-- TAMBAHKAN TOMBOL DONASI DI SINI -->
### ❤️ Support Development
If this tool helps your workflow, please consider supporting the developer.

[![Donate at Sociabuzz](https://img.shields.io/badge/Donate-Sociabuzz-%23d4af37?style=for-the-badge&logo=heart&logoColor=white)](https://sociabuzz.com/ns_metarefiner/donate)

---

**NS MetaRefiner** is a professional desktop application designed to streamline the workflow of stock photography contributors. By leveraging a **Hybrid AI Architecture**, it automates metadata generation and quality control sorting.

> **Developer:** eN-Es-Studio

---

## ✨ Key Features

### 🧠 Hybrid AI Engine
*   **Local Mode (Florence-2):** 100% offline processing. No API costs, unlimited usage.
*   **Cloud Mode:** Supports **Gemini, Groq, Mistral,** and **OpenAI** for high-precision analysis.

### 🗑️ Intelligent Smart Sorting
Automatically detects and separates defective images:
*   Watermarks & Signatures
*   AI Artifacts (extra fingers, distorted limbs)
*   Technical Issues (blur, noise, exposure errors)
*   Copyrighted text/Logos

### 🔍 SEO-Optimized Metadata
*   Generates descriptive titles automatically.
*   Creates 25-50 relevant commercial keywords.
*   Removes "stop words" and adds synonyms for better visibility.

### 📂 Multi-Agency CSV Export
Generates separate CSV files formatted for:
`Adobe Stock` • `Shutterstock` • `123RF` • `Vecteezy` • `Depositphotos` • `Freepik` • `Getty Images` • `Miri Canvas`

### 💾 Universal Metadata Embedding
Embeds IPTC/XMP metadata directly into files (JPEG, PNG, MP4, PDF) using Python libraries and ExifTool.

---

## 🚀 How to Use

1.  **Download** the latest release from the [Releases](https://github.com/eN-Es-Studio/NS-MetaRefiner/releases) page.
2.  **Extract** the ZIP file.
3.  Run `NS_MetaRefiner.exe`.
4.  Select your input files/folder.
5.  Choose your AI Engine (Local is recommended for speed).
6.  Click **START PROCESSING**.

---

## 📥 Download

Get the latest version of the application in the **Releases** section of this repository.

---

## ⚙️ Tech Stack

*   **Language:** Python 3.10
*   **GUI:** CustomTkinter
*   **AI Models:** Microsoft Florence-2, Google Gemini, Meta Llama (Groq), Mistral.
*   **Libraries:** Transformers, PyTorch, OpenCV, Pillow, PyMuPDF.

---

## 📜 License

This application is **FREE** and **Not For Sale**.
Intended to help the stock photography community.

© 2026 eN-Es-Studio. All Rights Reserved.
```

### **Penjelasan Kode Tombol Donasi:**

Baris kode ini:
```markdown
[![Donate at Sociabuzz](https://img.shields.io/badge/Donate-Sociabuzz-%23d4af37?style=for-the-badge&logo=heart&logoColor=white)](https://sociabuzz.com/ns_metarefiner/donate)
```

Artinya:
1.  `[ ... ]( ... )`: Ini adalah format link di Markdown.
2.  `![...](...)`: Ini adalah format gambar di Markdown.
3.  `https://img.shields.io/badge/...`: Ini link generator otomatis yang membuat gambar tombol berwarna Gold (`%23d4af37`) dengan ikon hati (`logo=heart`).
4.  Link tujuan: `https://sociabuzz.com/ns_metarefiner/donate`.

Hasilnya akan berupa tombol kuning keemasan bertuliskan "Donate Sociabuzz" dengan ikon hati yang bisa diklik.
