# AI Document Processing & Data Extraction

## Quick start

```bash
cd docproc
python -m venv venv 
.\venv\Scripts\Activate.ps1  
pip install -r requirements.txt
```
Get a Hugging Face token and make .env then set your

```bash
HF_TOKEN="your token"
HF_MODEL=Qwen/Qwen2.5-Coder-7B-Instruct (change the model if you want to)
LOW_CONFIDENCE_THRESHOLD=0.75
```
  OCR needs the Tesseract binary installed on your system (this is separate from the pytesseract Python package already in requirements.txt):
  download from https://github.com/UB-Mannheim/tesseract/wiki , then set TESSERACT_CMD in .env to the installed tesseract.exe path

```bash
  TESSERACT_CMD="set the tesseract.exe path here"
```

then 

```bash
Get-Content .env | ForEach-Object { if ($_ -match '^(.*?)=(.*)$') { [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2]) } }
```
# run your server using 

```bash
uvicorn app.main:app --reload   
```