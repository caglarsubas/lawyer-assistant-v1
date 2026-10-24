// Disposable Linux package tests. Invented bytes only; no server or valid model.
package manifest

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"github.com/ollama/ollama/types/model"
)

type integrityCase struct {
	ID       string `json:"id"`
	Fixture  string `json:"fixture"`
	Reader   string `json:"reader"`
	Expected string `json:"expected"`
}

func integritySum(b []byte) string {
	s := sha256.Sum256(b)
	return hex.EncodeToString(s[:])
}

func integrityWrite(t *testing.T, p string, b []byte) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(p), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(p, b, 0600); err != nil {
		t.Fatal(err)
	}
}

func integrityInventory(t *testing.T, root string) map[string]string {
	t.Helper()
	items := map[string]string{}
	err := filepath.WalkDir(root, func(p string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(root, p)
		if err != nil {
			return err
		}
		switch {
		case d.Type()&os.ModeSymlink != 0:
			target, err := os.Readlink(p)
			if err != nil {
				return err
			}
			items[rel] = "link:" + target
		case d.IsDir():
			items[rel] = "directory"
		default:
			b, err := os.ReadFile(p)
			if err != nil {
				return err
			}
			items[rel] = integritySum(b)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	return items
}

func integrityObserve(t *testing.T, c integrityCase) (string, bool) {
	t.Helper()
	arena := t.TempDir()
	root := filepath.Join(arena, "models")
	for _, p := range []string{"manifests", "manifests-v2", "blobs"} {
		if err := os.MkdirAll(filepath.Join(root, p), 0700); err != nil {
			t.Fatal(err)
		}
	}
	t.Setenv("OLLAMA_MODELS", root)
	config := []byte(`{"model_format":"gguf","model_family":"invented-U25","architecture":"arm64","os":"linux"}`)
	layer := []byte("GGUF-FRESH-U25-INVALID-AS-A-MODEL")
	configHash, layerHash := integritySum(config), integritySum(layer)
	data, err := json.Marshal(map[string]any{
		"schemaVersion": 2,
		"mediaType":     "application/vnd.docker.distribution.manifest.v2+json",
		"config":        map[string]any{"mediaType": "application/vnd.docker.container.image.v1+json", "digest": "sha256:" + configHash, "size": len(config)},
		"layers":        []any{map[string]any{"mediaType": "application/vnd.ollama.image.model", "digest": "sha256:" + layerHash, "size": len(layer)}},
		"annotation":    "fresh-manifest-U25",
	})
	if err != nil {
		t.Fatal(err)
	}
	if c.Fixture == "malformed_json" {
		data = []byte("{")
	}
	digest := integritySum(data)
	wanted := digest
	ref := "sha256-" + digest
	blob := filepath.Join(root, "blobs", ref)
	legacy := func(name string) string {
		return filepath.Join(root, "manifests", model.ParseName(name).Filepath())
	}
	integrityWrite(t, filepath.Join(root, "blobs", "sha256-"+configHash), config)
	if c.Fixture != "missing_layer" {
		integrityWrite(t, filepath.Join(root, "blobs", "sha256-"+layerHash), layer)
	}
	switch c.Fixture {
	case "valid_dash", "valid_file", "malformed_json", "missing_layer":
		integrityWrite(t, blob, data)
	case "appended_space":
		integrityWrite(t, blob, append(data, ' '))
	case "same_length_change":
		changed := []byte(strings.Replace(string(data), "fresh-manifest-U25", "fresh-manifest-X25", 1))
		if len(changed) != len(data) || integritySum(changed) == digest {
			t.Fatal("invalid same-size corruption fixture")
		}
		integrityWrite(t, blob, changed)
	case "replacement":
		integrityWrite(t, blob, []byte(strings.Replace(string(data), "fresh-manifest-U25", "another-manifest-U25", 1)))
	case "truncated":
		integrityWrite(t, blob, data[:len(data)-1])
	case "corrupt_prefix":
		integrityWrite(t, blob, append(data, '\n'))
		ref = digest[:12]
	case "valid_bare":
		integrityWrite(t, blob, data)
		ref = digest
	case "uppercase_reference":
		integrityWrite(t, blob, data)
		ref = "SHA256-" + strings.ToUpper(digest)
	case "absent":
	case "alias_no_fallback":
		integrityWrite(t, legacy(ref), data)
	case "named_regular", "named_formatting", "named_digestlike_tag":
		ref = "qualifier-u25:review"
		if c.Fixture == "named_formatting" {
			data = append(data, '\n')
		}
		if c.Fixture == "named_digestlike_tag" {
			ref = "qualifier-u25:sha256-" + digest
			data = append(data, ' ')
		}
		wanted = integritySum(data)
		integrityWrite(t, legacy(ref), data)
	case "named_symlink":
		integrityWrite(t, blob, data)
		ref = "qualifier-u25:linked"
		p := legacy(ref)
		if err := os.MkdirAll(filepath.Dir(p), 0700); err != nil {
			t.Fatal(err)
		}
		if err := os.Symlink(blob, p); err != nil {
			t.Fatal(err)
		}
	case "direct_symlink_other", "direct_symlink_outside":
		other := filepath.Join(arena, "outside", "sha256-"+digest)
		if c.Fixture == "direct_symlink_other" {
			data = append(data, ' ')
			other = filepath.Join(root, "blobs", "sha256-"+integritySum(data))
		}
		integrityWrite(t, other, data)
		if err := os.Symlink(other, blob); err != nil {
			t.Fatal(err)
		}
	case "direct_directory":
		if err := os.Mkdir(blob, 0700); err != nil {
			t.Fatal(err)
		}
	default:
		t.Fatal("unknown frozen fixture")
	}
	before := integrityInventory(t, arena)
	var got string
	var lookupErr error
	name := model.ParseName(ref)
	switch c.Reader {
	case "parse":
		var m *Manifest
		m, lookupErr = ParseNamedManifest(name)
		if lookupErr == nil && m != nil {
			got = m.Digest()
		}
	case "data":
		var b []byte
		b, lookupErr = ReadManifestData(name)
		if lookupErr == nil {
			got = integritySum(b)
		}
	case "file":
		var p, base string
		p, base, lookupErr = resolveManifestPath(name)
		if lookupErr == nil {
			var f *os.File
			f, got, lookupErr = openVerifiedManifestLocked(p, base)
			if lookupErr == nil {
				b, err := io.ReadAll(f)
				closeErr := f.Close()
				if err != nil || closeErr != nil || integritySum(b) != got {
					t.Fatal("invalid verified file or close")
				}
			}
		}
	default:
		t.Fatal("unknown reader")
	}
	actual := "mismatched"
	switch {
	case errors.Is(lookupErr, os.ErrNotExist):
		actual = "missing"
	case lookupErr != nil:
		actual = "rejected"
	case got == wanted:
		actual = "matched"
	}
	return actual, reflect.DeepEqual(before, integrityInventory(t, arena))
}

func TestFreshFrozenManifestIntegrity(t *testing.T) {
	variant := os.Getenv("MANIFEST_VARIANT")
	if variant != "baseline" && variant != "patched" {
		t.Fatal("explicit variant required")
	}
	raw, err := os.ReadFile("integrity_cases.json")
	if err != nil {
		t.Fatal(err)
	}
	var catalog struct {
		Cases []integrityCase `json:"cases"`
	}
	if err := json.Unmarshal(raw, &catalog); err != nil || len(catalog.Cases) != 20 {
		t.Fatal("frozen inventory required")
	}
	for _, c := range catalog.Cases {
		t.Run(c.ID, func(t *testing.T) {
			actual, unchanged := integrityObserve(t, c)
			b, err := json.Marshal(map[string]any{"id": c.ID, "variant": variant, "reader": c.Reader, "actual": actual, "store_unchanged": unchanged})
			if err != nil {
				t.Fatal(err)
			}
			t.Log("INTEGRITY_RESULT " + string(b))
			if actual != c.Expected || !unchanged {
				t.Error("unexpected result or scratch-store mutation")
			}
		})
	}
}
