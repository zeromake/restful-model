build:
	rm -rf ./dist
	python setup.py sdist
	python setup.py bdist_wheel
	python setup.py bdist_egg
