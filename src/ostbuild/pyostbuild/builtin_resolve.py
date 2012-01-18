# Copyright (C) 2011 Colin Walters <walters@verbum.org>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

import os,sys,subprocess,tempfile,re,shutil
import argparse
import json
import urlparse
from StringIO import StringIO

from . import builtins
from .ostbuildlog import log, fatal
from .subprocess_helpers import run_sync, run_sync_get_output
from . import ostbuildrc
from . import buildutil
from . import kvfile
from . import odict

class OstbuildResolve(builtins.Builtin):
    name = "resolve"
    short_description = "Download the source code for a given manifest"

    def __init__(self):
        builtins.Builtin.__init__(self)

    def _ensure_vcs_mirror(self, keytype, uri, branch):
        assert keytype == 'git'
        parsed = urlparse.urlsplit(uri)
        mirror = os.path.join(self.mirrordir, keytype, parsed.scheme, parsed.netloc, parsed.path[1:])
        tmp_mirror = mirror + '.tmp'
        if os.path.isdir(tmp_mirror):
            shutil.rmtree(tmp_mirror)
        if not os.path.isdir(mirror):
            run_sync(['git', 'clone', '--mirror', uri, tmp_mirror])
            run_sync(['git', 'config', 'gc.auto', '0'], cwd=tmp_mirror)
            os.rename(tmp_mirror, mirror)
        last_fetch_path = mirror + '.lastfetch'
        if os.path.exists(last_fetch_path):
            f = open(last_fetch_path)
            last_fetch_contents = f.read()
            f.close()
            last_fetch_contents = last_fetch_contents.strip()
        else:
            last_fetch_contents = None
        current_vcs_version = run_sync_get_output(['git', 'rev-parse', branch], cwd=mirror)
        current_vcs_version = current_vcs_version.strip()
        if current_vcs_version != last_fetch_contents:
            log("last fetch %r differs from branch %r" % (last_fetch_contents, current_vcs_version))
            tmp_checkout = os.path.join(self.mirrordir, '_tmp-checkouts', keytype, parsed.netloc, parsed.path[1:])
            if os.path.isdir(tmp_checkout):
                shutil.rmtree(tmp_checkout)
            parent = os.path.dirname(tmp_checkout)
            if not os.path.isdir(parent):
                os.makedirs(parent)
            run_sync(['git', 'clone', '-q', '--no-checkout', mirror, tmp_checkout])
            run_sync(['git', 'checkout', '-q', '-f', current_vcs_version], cwd=tmp_checkout)
            submodules = []
            submodules_status_text = run_sync_get_output(['git', 'submodule', 'status'], cwd=tmp_checkout)
            submodule_status_lines = submodules_status_text.split('\n')
            for line in submodule_status_lines:
                if line == '': continue
                line = line[1:]
                (sub_checksum, sub_name) = line.split(' ', 1)
                sub_url = run_sync_get_output(['git', 'config', '-f', '.gitmodules',
                                               'submodule.%s.url' % (sub_name, )], cwd=tmp_checkout)
                self._ensure_vcs_mirror(keytype, sub_url, sub_checksum)
            shutil.rmtree(tmp_checkout)
            f = open(last_fetch_path, 'w')
            f.write(current_vcs_version + '\n')
            f.close()
        return mirror

    def _parse_src_key(self, srckey):
        idx = srckey.find(':')
        if idx < 0:
            raise ValueError("Invalid SRC uri=%s" % (srckey, ))
        keytype = srckey[:idx]
        if keytype not in ['git']:
            raise ValueError("Unsupported SRC uri=%s" % (srckey, ))
        uri = srckey[idx+1:]
        return (keytype, uri)

    def _resolve_component_meta(self, component_meta):
        result = dict(component_meta)
        orig_src = component_meta['src']

        did_expand = False
        for (vcsprefix, expansion) in self.manifest['vcsconfig'].iteritems():
            prefix = vcsprefix + ':'
            if orig_src.startswith(prefix):
                result['src'] = expansion + orig_src[len(prefix):]
                did_expand = True
                break

        name = component_meta.get('name')
        if name is None:
            if did_expand:
                src = orig_src
                idx = src.rindex(':')
                name = src[idx+1:]
            else:
                src = result['src']
                idx = src.rindex('/')
                name = src[idx+1:]
            if name.endswith('.git'):
                name = name[:-4]
            name = name.replace('/', '-')
            result['name'] = name

        if 'branch' not in result:
            result['branch'] = 'master'

        return result
    
    def execute(self, argv):
        parser = argparse.ArgumentParser(description=self.short_description)
        parser.add_argument('--fetch', action='store_true')
        parser.add_argument('components', nargs='*')

        args = parser.parse_args(argv)
        self.args = args
        
        self.parse_config()

        manifest_path = self.ostbuildrc.get_key('manifest')
        self.manifest = json.load(open(manifest_path))

        self.resolved_components = map(self._resolve_component_meta, self.manifest['components'])

        if args.fetch:
            if len(args.components) == 0:
                fetch_components = map(lambda x: x['name'], self.resolved_components)
            else:
                fetch_components = args.components
            for component_name in fetch_components:
                found = False
                for component in self.resolved_components:
                    if component['name'] == component_name:
                        found = True
                        break
                if not found:
                    fatal("Unknown component %r" % (component_name, ))
                (keytype, uri) = self._parse_src_key(component['src'])
                mirrordir = self._ensure_vcs_mirror(keytype, uri, component['branch'])
                log("Running git fetch for %s" % (component['name'], ))
                run_sync(['git', 'fetch'], cwd=mirrordir, log_initiation=False)
        else:
            fetch_components = []

        for component in self.resolved_components:
            (keytype, uri) = self._parse_src_key(component['src'])
            try:
                fetch_components.index(component['name'])
            except ValueError, e:
                mirrordir = self._ensure_vcs_mirror(keytype, uri, component['branch'])
            revision = buildutil.get_git_version_describe(mirrordir,
                                                          component['branch'])
            component['revision'] = revision

        mirror_gitconfig_path = os.path.join(self.mirrordir, 'gitconfig')
        git_mirrordir = os.path.join(self.mirrordir, 'git')
        f = open(mirror_gitconfig_path, 'w')
        find_proc = subprocess.Popen(['find', '-type', 'f', '-name', 'HEAD'],
                                     cwd=git_mirrordir, stdout=subprocess.PIPE)
        path_to_url_re = re.compile(r'^([^/]+)/([^/]+)/(.+)$')
        for line in find_proc.stdout:
            assert line.startswith('./')
            path = line[2:-6]
            f.write('[url "')
            f.write('file://' + os.path.join(git_mirrordir, path) + '/')
            f.write('"]\n')
            f.write('   insteadOf = ')
            match = path_to_url_re.match(path)
            assert match is not None
            url = urlparse.urlunparse([match.group(1), match.group(2), match.group(3),
                                       None, None, None])
            f.write(url)
            f.write('/\n')
        print "Generated git mirror config: %s" % (mirror_gitconfig_path, )

        self.manifest['components'] = self.resolved_components

        out_manifest = os.path.join(self.workdir, 'manifest.json')
        patchdir = os.path.join(self.workdir, 'patches')
        if not os.path.isdir(patchdir):
            os.mkdir(patchdir)
        all_patches = {}
        for component in self.resolved_components:
            patches = component.get('patches', [])
            for patch in patches:
                all_patches[patch] = True
        for patch in all_patches:
            src = os.path.join(os.path.dirname(manifest_path),
                               patch)
            dest = os.path.join(patchdir, patch)
            shutil.copy(src, dest)
        
        f = open(out_manifest, 'w')
        json.dump(self.manifest, f, indent=4)
        f.close()
        print "Created: %s, %d patches" % (out_manifest, len(all_patches.keys()))
        
builtins.register(OstbuildResolve)
