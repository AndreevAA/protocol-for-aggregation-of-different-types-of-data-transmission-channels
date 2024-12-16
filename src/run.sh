python3 -m venv myenv

source myenv/bin/activate

pip3 install --upgrade pip
pip3 install -r requirements.txt

python3 __main__.py

deactivate
