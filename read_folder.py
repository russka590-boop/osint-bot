import os, sys, argparse
from pathlib import Path

CODE_EXTENSIONS = {'.py','.js','.ts','.jsx','.tsx','.java','.c','.cpp','.cc','.cxx','.h','.hpp','.cs','.go','.rs','.rb','.php','.html','.htm','.css','.scss','.sass','.less','.json','.yaml','.yml','.toml','.ini','.cfg','.md','.txt','.sh','.bash','.zsh','.sql','.xml','.kt','.swift','.m','.mm','.pl','.lua','.r','.vue','.svelte'}
SKIP_DIRS = {'.git','.svn','.hg','node_modules','__pycache__','.venv','venv','env','.env','dist','build','target','bin','obj','.idea','.vscode','.mypy_cache','.pytest_cache','.tox','coverage','.next','.nuxt'}
MAX_FILE_SIZE = 1024*1024

def is_binary(p):
    try:
        with open(p,'rb') as f: chunk=f.read(1024)
        if b'\x00' in chunk: return True
        chunk.decode('utf-8'); return False
    except (UnicodeDecodeError,OSError): return True

def collect_files(root, exts, max_size):
    files=[]
    for dp,dn,fn in os.walk(root):
        dn[:]=[d for d in dn if d not in SKIP_DIRS and not d.startswith('.')]
        for name in fn:
            p=Path(dp)/name
            if p.suffix.lower() not in exts: continue
            try:
                if p.stat().st_size>max_size: continue
            except OSError: continue
            if is_binary(p): continue
            files.append(p)
    return sorted(files)

def read_file(p):
    try:
        with open(p,'r',encoding='utf-8',errors='replace') as f: return f.read()
    except OSError as e: return f'<<Ошибка чтения: {e}>>'

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('root',nargs='?',default='.')
    ap.add_argument('-o','--output')
    ap.add_argument('-e','--ext',action='append')
    ap.add_argument('--max-size',type=int,default=MAX_FILE_SIZE)
    ap.add_argument('--list',action='store_true')
    a=ap.parse_args()
    root=Path(a.root).resolve()
    if not root.is_dir(): print(f'Ошибка: {root} не папка',file=sys.stderr); sys.exit(1)
    exts=set(CODE_EXTENSIONS)
    if a.ext:
        for e in a.ext: exts.add(e if e.startswith('.') else '.'+e)
    files=collect_files(root,exts,a.max_size)
    if not files: print('Файлы не найдены.',file=sys.stderr); sys.exit(0)
    out=open(a.output,'w',encoding='utf-8') if a.output else sys.stdout
    try:
        if a.list:
            for f in files: print(f.relative_to(root),file=out)
        else:
            for f in files:
                print(f"\n{'='*80}",file=out); print(f'ФАЙЛ: {f.relative_to(root)}',file=out); print(f"{'='*80}\n",file=out); print(read_file(f),file=out)
    finally:
        if a.output: out.close(); print(f'Сохранено: {a.output}',file=sys.stderr)

if __name__=='__main__': main()
