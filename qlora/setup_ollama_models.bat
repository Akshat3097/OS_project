@echo off
REM Creates the customized tutor models in Ollama. Run from the project folder (double-click works too).
cd /d "%~dp0\.."
ollama pull llama3.1:8b
echo.
echo Creating os-tutor-prompt (instructions + examples, no training)...
ollama create os-tutor-prompt -f qlora\Modelfile.prompt
if exist qlora\os-tutor.gguf (
  echo.
  echo Found the fine-tuned model file. Creating os-tutor ^(fine-tuned^)...
  python -m qlora.create_finetuned
) else (
  echo.
  echo No fine-tuned model yet: save os-tutor.gguf from Google Drive as qlora\os-tutor.gguf and run this again.
)
echo.
echo Done. Try:   ollama run os-tutor-prompt
echo   or:        python -m qlora.compare
pause
