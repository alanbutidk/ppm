"""
CloneRepoHandler for ppm.
A minimal, dependency-free Git clone implementation using the Git
"smart HTTP" protocol (v2), speaking directly to the remote over
urllib. No system 'git' binary is required, so this works on any
OS ppm itself runs on.

Copyright (c) 2026 Alan. All Rights Reserved.
"""

from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import hashlib
import struct
import zlib
import re


class CloneError(Exception):
    pass


def _normalize_url(url: str) -> str:
    """Accepts short 'user/repo' GitHub form or a full URL, returns a full HTTPS URL."""
    url = url.strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url.rstrip("/")
    if re.fullmatch(r"[\w.-]+/[\w.-]+", url):
        return f"https://github.com/{url}"
    raise CloneError(f"Unrecognized repository reference: {url}")


class CloneRepoHandler:
    """Clones a remote git repository into a local directory using the
    smart HTTP v2 protocol, without invoking any external git binary."""

    def __init__(self, url: str, dest: str, branch: str = None):
        self.url = _normalize_url(url)
        if not self.url.endswith(".git"):
            self.info_refs_url = f"{self.url}.git/info/refs?service=git-upload-pack"
            self.upload_pack_url = f"{self.url}.git/git-upload-pack"
        else:
            self.info_refs_url = f"{self.url}/info/refs?service=git-upload-pack"
            self.upload_pack_url = f"{self.url}/git-upload-pack"
        self.dest = Path(dest)
        self.branch = branch
        self.objects = {}  # sha1 hex -> (type_name, content bytes)

    # -- pkt-line helpers --------------------------------------------------

    @staticmethod
    def _pkt_line(data: bytes) -> bytes:
        if data == b"":
            return b"0000"
        length = len(data) + 4
        return f"{length:04x}".encode() + data

    @staticmethod
    def _parse_pkt_lines(raw: bytes):
        lines = []
        i = 0
        while i < len(raw):
            length_hex = raw[i:i + 4]
            if len(length_hex) < 4:
                break
            try:
                length = int(length_hex, 16)
            except ValueError:
                break
            if length == 0:
                lines.append(None)  # flush-pkt marker
                i += 4
                continue
            lines.append(raw[i + 4:i + length])
            i += length
        return lines

    # -- network -------------------------------------------------------------

    def _http_get(self, url: str) -> bytes:
        req = Request(url, headers={"Git-Protocol": "version=2", "User-Agent": "ppm-clone/1.0"})
        try:
            with urlopen(req, timeout=15) as resp:
                return resp.read()
        except HTTPError as e:
            raise CloneError(f"HTTP error fetching {url}: {e.code} {e.reason}")
        except URLError as e:
            raise CloneError(f"Network error fetching {url}: {e.reason}")

    def _http_post(self, url: str, body: bytes, content_type: str) -> bytes:
        req = Request(
            url,
            data=body,
            headers={
                "Content-Type": content_type,
                "Git-Protocol": "version=2",
                "User-Agent": "ppm-clone/1.0",
                "Accept": "application/x-git-upload-pack-result",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=30) as resp:
                return resp.read()
        except HTTPError as e:
            raise CloneError(f"HTTP error posting to {url}: {e.code} {e.reason}")
        except URLError as e:
            raise CloneError(f"Network error posting to {url}: {e.reason}")

    # -- protocol steps --------------------------------------------------

    def _discover_refs(self) -> dict:
        """Runs the v2 ref discovery handshake, returns {refname: sha1hex}."""
        raw = self._http_get(self.info_refs_url)
        lines = self._parse_pkt_lines(raw)
        # First line should be '# service=git-upload-pack'; ignore up to first flush.
        idx = 0
        while idx < len(lines) and lines[idx] is not None:
            idx += 1
        idx += 1  # skip the flush-pkt

        remaining = lines[idx:]
        is_v2 = any(l == b"version 2\n" or l == b"version 2" for l in remaining if l)

        if not is_v2:
            # Fallback: parse v0/v1 style ref advertisement directly.
            refs = {}
            for l in remaining:
                if not l:
                    continue
                text = l.decode(errors="replace").strip("\n")
                if "\x00" in text:
                    text = text.split("\x00", 1)[0]
                parts = text.split(" ", 1)
                if len(parts) == 2 and re.fullmatch(r"[0-9a-f]{40}", parts[0]):
                    refs[parts[1]] = parts[0]
            return refs

        # v2: request ls-refs
        body = (
            self._pkt_line(b"command=ls-refs\n")
            + self._pkt_line(b"agent=ppm-clone/1.0\n")
            + b"0001"  # delim-pkt
            + self._pkt_line(b"peel\n")
            + self._pkt_line(b"symrefs\n")
            + self._pkt_line(b"ref-prefix refs/heads/\n")
            + self._pkt_line(b"ref-prefix refs/tags/\n")
            + self._pkt_line(b"ref-prefix HEAD\n")
            + self._pkt_line(b"")
        )
        resp = self._http_post(self.info_refs_url.split("?")[0].replace("info/refs", "git-upload-pack"), body,
                                "application/x-git-upload-pack-request")
        refs = {}
        for l in self._parse_pkt_lines(resp):
            if not l:
                continue
            text = l.decode(errors="replace").strip("\n")
            parts = text.split(" ", 1)
            if len(parts) == 2 and re.fullmatch(r"[0-9a-f]{40}", parts[0]):
                name = parts[1].split(" ")[0]
                refs[name] = parts[0]
        return refs

    def _fetch_pack(self, want_sha: str) -> bytes:
        """Requests a packfile for the given commit sha, using v2 fetch.
        The response is pkt-line framed and may use sideband multiplexing
        (channel 1 = pack data, channel 2 = progress, channel 3 = error),
        so we must reassemble it properly rather than scanning for 'PACK'."""
        body = (
            self._pkt_line(b"command=fetch\n")
            + self._pkt_line(b"agent=ppm-clone/1.0\n")
            + b"0001"
            + self._pkt_line(f"want {want_sha}\n".encode())
            + self._pkt_line(b"done\n")
            + self._pkt_line(b"no-progress\n")
            + self._pkt_line(b"")
        )
        resp = self._http_post(self.upload_pack_url, body, "application/x-git-upload-pack-request")

        pack_chunks = []
        i = 0
        seen_packfile_section = False
        while i < len(resp):
            length_hex = resp[i:i + 4]
            if len(length_hex) < 4:
                break
            try:
                length = int(length_hex, 16)
            except ValueError:
                break
            if length == 0:  # flush-pkt
                i += 4
                continue
            if length == 1:  # delim-pkt
                i += 4
                continue
            payload = resp[i + 4:i + length]
            i += length

            if not seen_packfile_section:
                if payload.strip() == b"packfile":
                    seen_packfile_section = True
                continue

            # Sideband demux: first byte is the channel number.
            if payload:
                channel = payload[0]
                data = payload[1:]
                if channel == 1:
                    pack_chunks.append(data)
                elif channel == 3:
                    raise CloneError(f"Remote error: {data.decode(errors='replace')}")
                # channel 2 (progress) is ignored

        pack = b"".join(pack_chunks)
        pack_start = pack.find(b"PACK")
        if pack_start == -1:
            raise CloneError("No packfile magic found in server response; clone failed.")
        return pack[pack_start:]

    # -- packfile parsing --------------------------------------------------

    _OBJ_TYPES = {1: "commit", 2: "tree", 3: "blob", 4: "tag", 6: "ofs_delta", 7: "ref_delta"}

    def _parse_packfile(self, pack: bytes):
        if pack[:4] != b"PACK":
            raise CloneError("Invalid packfile signature.")
        _version, num_objects = struct.unpack(">II", pack[4:12])
        offset = 12
        offset_index = {}  # start offset -> (type, content) for ofs_delta resolution

        for _ in range(num_objects):
            start_offset = offset
            byte = pack[offset]
            offset += 1
            obj_type = (byte >> 4) & 0x7
            size = byte & 0x0F
            shift = 4
            while byte & 0x80:
                byte = pack[offset]
                offset += 1
                size |= (byte & 0x7F) << shift
                shift += 7

            if obj_type == 6:  # ofs_delta
                byte = pack[offset]
                offset += 1
                neg_offset = byte & 0x7F
                while byte & 0x80:
                    byte = pack[offset]
                    offset += 1
                    neg_offset = ((neg_offset + 1) << 7) | (byte & 0x7F)
                base_offset = start_offset - neg_offset
                decompressed, consumed = self._inflate(pack, offset)
                offset += consumed
                base_type, base_content = offset_index[base_offset]
                content = self._apply_delta(base_content, decompressed)
                offset_index[start_offset] = (base_type, content)
                sha = hashlib.sha1(f"{base_type} {len(content)}\0".encode() + content).hexdigest()
                self.objects[sha] = (base_type, content)

            elif obj_type == 7:  # ref_delta
                base_sha = pack[offset:offset + 20].hex()
                offset += 20
                decompressed, consumed = self._inflate(pack, offset)
                offset += consumed
                base_type, base_content = self.objects[base_sha]
                content = self._apply_delta(base_content, decompressed)
                offset_index[start_offset] = (base_type, content)
                sha = hashlib.sha1(f"{base_type} {len(content)}\0".encode() + content).hexdigest()
                self.objects[sha] = (base_type, content)

            else:
                type_name = self._OBJ_TYPES[obj_type]
                decompressed, consumed = self._inflate(pack, offset)
                offset += consumed
                offset_index[start_offset] = (type_name, decompressed)
                sha = hashlib.sha1(f"{type_name} {len(decompressed)}\0".encode() + decompressed).hexdigest()
                self.objects[sha] = (type_name, decompressed)

    @staticmethod
    def _inflate(data: bytes, offset: int):
        d = zlib.decompressobj()
        result = d.decompress(data[offset:])
        consumed = len(data[offset:]) - len(d.unused_data)
        return result, consumed

    @staticmethod
    def _apply_delta(base: bytes, delta: bytes) -> bytes:
        pos = 0

        def read_varint():
            nonlocal pos
            result = 0
            shift = 0
            while True:
                byte = delta[pos]
                pos += 1
                result |= (byte & 0x7F) << shift
                shift += 7
                if not (byte & 0x80):
                    break
            return result

        _src_size = read_varint()
        _dst_size = read_varint()
        out = bytearray()

        while pos < len(delta):
            opcode = delta[pos]
            pos += 1
            if opcode & 0x80:
                copy_offset = 0
                copy_size = 0
                for i in range(4):
                    if opcode & (1 << i):
                        copy_offset |= delta[pos] << (8 * i)
                        pos += 1
                for i in range(3):
                    if opcode & (1 << (4 + i)):
                        copy_size |= delta[pos] << (8 * i)
                        pos += 1
                if copy_size == 0:
                    copy_size = 0x10000
                out += base[copy_offset:copy_offset + copy_size]
            elif opcode != 0:
                out += delta[pos:pos + opcode]
                pos += opcode
            else:
                raise CloneError("Invalid delta opcode 0 encountered.")
        return bytes(out)

    # -- object graph walk & checkout --------------------------------------------------

    def _checkout_tree(self, tree_sha: str, target_dir: Path):
        target_dir.mkdir(parents=True, exist_ok=True)
        _type, content = self.objects[tree_sha]
        i = 0
        while i < len(content):
            space = content.index(b" ", i)
            mode = content[i:space].decode()
            null = content.index(b"\0", space)
            name = content[space + 1:null].decode(errors="replace")
            sha_bytes = content[null + 1:null + 21]
            sha = sha_bytes.hex()
            i = null + 21

            entry_type, entry_content = self.objects.get(sha, (None, None))
            if mode.startswith("4"):  # directory (tree)
                self._checkout_tree(sha, target_dir / name)
            elif mode == "120000":  # symlink; write target text as plain file to stay portable
                (target_dir / name).write_bytes(entry_content or b"")
            else:  # regular file / blob
                (target_dir / name).write_bytes(entry_content or b"")
                if mode == "100755":
                    try:
                        (target_dir / name).chmod(0o755)
                    except OSError:
                        pass

    def clone(self) -> str:
        """Performs the clone. Returns the commit sha that was checked out."""
        refs = self._discover_refs()
        if not refs:
            raise CloneError("Remote reported no refs; repository may not exist or is empty.")

        target_ref = None
        if self.branch:
            target_ref = refs.get(f"refs/heads/{self.branch}")
            if target_ref is None:
                raise CloneError(f"Branch '{self.branch}' not found on remote.")
        else:
            for candidate in ("refs/heads/main", "refs/heads/master"):
                if candidate in refs:
                    target_ref = refs[candidate]
                    break
            if target_ref is None:
                head_candidates = [v for k, v in refs.items() if k.startswith("refs/heads/")]
                if head_candidates:
                    target_ref = head_candidates[0]
        if target_ref is None:
            raise CloneError("Could not resolve a branch to clone.")

        pack = self._fetch_pack(target_ref)
        self._parse_packfile(pack)

        commit_type, commit_content = self.objects[target_ref]
        if commit_type != "commit":
            raise CloneError(f"Expected commit object, got {commit_type}.")

        tree_line = next(line for line in commit_content.split(b"\n") if line.startswith(b"tree "))
        tree_sha = tree_line.split(b" ", 1)[1].decode()

        self._checkout_tree(tree_sha, self.dest)
        return target_ref
