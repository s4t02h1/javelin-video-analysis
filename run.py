
#!/usr/bin/env python3
"""
Compatibility launcher to keep `python run.py` working.
Delegates to jva.run.main.
"""

from jva.run import main

if __name__ == "__main__":
	main()
