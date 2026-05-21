<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NS MetaRefiner - Intelligent Metadata & Sorting</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
            line-height: 1.6;
            color: #e6edf3;
            background-color: #0d1117;
            margin: 0;
            padding: 0;
        }
        .container {
            max-width: 800px;
            margin: 40px auto;
            padding: 40px;
            background-color: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            box-shadow: 0 8px 24px rgba(1, 4, 9, 0.5);
        }
        h1, h2, h3 {
            color: #ffffff;
            margin-top: 24px;
            margin-bottom: 16px;
            font-weight: 600;
        }
        h1 { font-size: 32px; border-bottom: 1px solid #21262d; padding-bottom: 10px; }
        h2 { font-size: 24px; border-bottom: 1px solid #21262d; padding-bottom: 8px; margin-top: 40px; }
        h3 { font-size: 20px; color: #58a6ff; margin-top: 24px; }
        p { margin-bottom: 16px; }
        a { color: #58a6ff; text-decoration: none; }
        a:hover { text-decoration: underline; }
        
        /* Badges Styling */
        .badges img {
            vertical-align: middle;
            margin-right: 5px;
            margin-bottom: 5px;
        }

        /* Donation Box */
        .donation-box {
            background-color: #21262d;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 20px;
            text-align: center;
            margin: 20px 0 30px 0;
        }
        .btn-donate {
            display: inline-block;
            background-color: #d4af37; /* Gold */
            color: #000000;
            font-weight: bold;
            padding: 12px 25px;
            border-radius: 6px;
            text-decoration: none;
            margin-top: 10px;
            transition: background-color 0.2s;
        }
        .btn-donate:hover {
            background-color: #e6c453;
            text-decoration: none;
        }

        /* List Styling */
        ul, ol {
            padding-left: 25px;
        }
        li {
            margin-bottom: 8px;
        }

        /* Code Inline */
        code {
            background-color: rgba(110, 118, 129, 0.4);
            padding: 3px 6px;
            border-radius: 4px;
            font-family: ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, monospace;
            font-size: 85%;
        }

        /* Footer */
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #21262d;
            text-align: center;
            color: #8b949e;
            font-size: 14px;
        }
    </style>
</head>
<body>

<div class="container">

    <!-- Header Section -->
    <h1>NS MetaRefiner</h1>
    
    <div class="badges">
        <img src="https://img.shields.io/badge/version-1.0.0-blue" alt="Version">
        <img src="https://img.shields.io/badge/platform-Windows-lightgrey" alt="Platform">
        <img src="https://img.shields.io/badge/license-Free-green" alt="License">
    </div>

    <!-- Donation Section -->
    <div class="donation-box">
        <h3>❤️ Support Development</h3>
        <p>If this tool helps your workflow, please
