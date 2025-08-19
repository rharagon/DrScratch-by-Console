# Dr. Scratch by Console

<img width="1012" height="359" alt="Local De" src="https://github.com/user-attachments/assets/b3314297-e65a-4083-a656-6150fa33e77a" />


**Dr. Scratch** is an analysis tool that evaluates your Scratch projects across various computational areas to provide feedback on aspects such as abstraction, logical thinking, synchronization, parallelism, flow control, user interactivity, and data representation. This analyzer is useful for assessing both your own projects and those of your students.

You can try a beta version at [https://drscratch.org](https://drscratch.org).

**Dr. Scratch by Console** is the console app to get the metrics

---

## Console Analyzers

The repository includes command-line tools for batch analysing `.sb3` projects:

- `console_analyzer.py` – processes projects sequentially. Use the '-h' option to show help.
- `console_analyzer_multiprocess.py` – uses multiple processes and adds a `--processes` option to control workers.
