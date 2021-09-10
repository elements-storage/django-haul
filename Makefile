.PHONY: clean clean-test clean-pyc clean-build docs lint

clean: clean-build clean-pyc clean-test ## remove all build, test, coverage and Python artifacts

clean-build: ## remove build artifacts
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -f {} +

clean-pyc: ## remove Python file artifacts
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test: ## remove test and coverage artifacts
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/
	rm -fr .pytest_cache

lint: ## check style with flake8
	flake8 haul tests

test: ## run tests quickly with the default Python
	pytest tests

coverage: ## check code coverage quickly with the default Python
	pytest --cov=haul tests
	coverage html
	open htmlcov/index.html || xdg-open htmlcov/index.html

docs: ## generate Sphinx HTML documentation, including API docs
	rm -f docs/haul.rst
	rm -f docs/modules.rst
	sphinx-apidoc -o docs/ haul
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
	open docs/_build/html/index.html

servedocs: docs ## compile the docs watching for changes
	watchmedo shell-command -p '*.rst;*.py' -c '$(MAKE) -C docs html' -R -D .

release: dist ## package and upload a release
	twine upload dist/*

dist: clean ## builds source and wheel package
	python setup.py sdist
	python setup.py bdist_wheel
	ls -l dist

install: clean ## install the package to the active Python's site-packages
	python setup.py install
