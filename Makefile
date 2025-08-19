.PHONY: install
install:
	@echo "Installing dependencies..."
	@pip install -r requirements.txt --target ./package

package: install
	@echo "Creating zip package..."
	@zip -r functions.zip handlers/ package/