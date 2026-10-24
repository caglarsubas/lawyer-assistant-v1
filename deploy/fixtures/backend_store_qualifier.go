// Isolated package qualification. No server, HTTP client, inference or real model.
package qualifier

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"github.com/ollama/ollama/manifest"
	"github.com/ollama/ollama/types/model"
)

type fixtureCase struct {
	ID       string            `json:"id"`
	Fixture  string            `json:"fixture"`
	Expected map[string]string `json:"expected"`
}

type outcome struct {
	ID        string `json:"id"`
	Profile   string `json:"profile"`
	Actual    string `json:"actual"`
	Unchanged bool   `json:"store_unchanged"`
}

func sum(b []byte) string {
	s := sha256.Sum256(b)
	return hex.EncodeToString(s[:])
}

func write(t *testing.T, path string, data []byte) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, data, 0600); err != nil {
		t.Fatal(err)
	}
}

func inventory(t *testing.T, root string) map[string]string {
	t.Helper()
	result := map[string]string{}
	err := filepath.WalkDir(root, func(p string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(root, p)
		if err != nil {
			return err
		}
		if d.IsDir() {
			result[rel] = "directory"
		} else {
			b, err := os.ReadFile(p)
			if err != nil {
				return err
			}
			result[rel] = sum(b)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	return result
}

func inspect(t *testing.T, kind string) (string, bool) {
	t.Helper()
	root := t.TempDir()
	// Both package versions may ensure these roots exist; no real store is mounted.
	for _, p := range []string{"manifests", "manifests-v2", "blobs"} {
		if err := os.MkdirAll(filepath.Join(root, p), 0700); err != nil {
			t.Fatal(err)
		}
	}
	t.Setenv("OLLAMA_MODELS", root)
	config := []byte(`{"model_format":"gguf","model_family":"invented","architecture":"arm64","os":"linux"}`)
	layer := []byte("GGUF-INVENTED-NOT-A-MODEL-Q2401")
	configHash, layerHash := sum(config), sum(layer)
	data, err := json.Marshal(map[string]any{
		"schemaVersion": 2,
		"mediaType": "application/vnd.docker.distribution.manifest.v2+json",
		"config": map[string]any{"mediaType": "application/vnd.docker.container.image.v1+json", "digest": "sha256:" + configHash, "size": len(config)},
		"layers": []any{map[string]any{"mediaType": "application/vnd.ollama.image.model", "digest": "sha256:" + layerHash, "size": len(layer)}},
	})
	if err != nil {
		t.Fatal(err)
	}
	digest := sum(data)
	name := "qualifier:latest"
	legacy := func(ref string) string {
		return filepath.Join(root, "manifests", model.ParseName(ref).Filepath())
	}
	blob := filepath.Join(root, "blobs", "sha256-"+digest)
	write(t, filepath.Join(root, "blobs", "sha256-"+configHash), config)
	if kind != "missing_layer_named" {
		write(t, filepath.Join(root, "blobs", "sha256-"+layerHash), layer)
	}
	switch kind {
	case "named_parser", "colon_parser", "dash_parser", "empty_named":
	case "legacy_named", "missing_layer_named":
		write(t, legacy(name), data)
	case "invalid_json_named":
		write(t, legacy(name), []byte("{"))
	case "dash_legacy_only":
		write(t, legacy(name), data)
		name = "sha256-" + digest
	case "colon_alias":
		name = "sha256:" + digest
		// An ordinary named alias can point to other valid bytes. It is not a pin.
		write(t, legacy(name), append(data, ' '))
	case "colon_blob", "dash_blob", "bare_blob", "short_blob", "ambiguous_prefix", "tampered_blob":
		write(t, blob, data)
		switch kind {
		case "colon_blob":
			name = "sha256:" + digest
		case "dash_blob", "tampered_blob":
			name = "sha256-" + digest
		case "bare_blob":
			name = digest
		default:
			name = digest[:12]
		}
		if kind == "tampered_blob" {
			write(t, blob, append(data, ' '))
		}
		if kind == "ambiguous_prefix" {
			other := digest[:12] + strings.Repeat("0", 52)
			if other == digest {
				t.Fatal("sentinel collision")
			}
			write(t, filepath.Join(root, "blobs", "sha256-"+other), data)
		}
	default:
		t.Fatal("unknown frozen fixture")
	}
	before := inventory(t, root)
	actual := ""
	switch kind {
	case "named_parser":
		if model.ParseName(name).IsFullyQualified() {
			actual = "valid"
		}
	case "dash_parser":
		if model.ParseName("sha256-" + digest).IsFullyQualified() {
			actual = "valid"
		}
	case "colon_parser":
		n := model.ParseName("sha256:" + digest)
		if n.Model == "sha256" && n.Tag == digest && n.IsFullyQualified() {
			actual = "ordinary_tag"
		}
	default:
		m, err := manifest.ParseNamedManifest(model.ParseName(name))
		switch {
		case errors.Is(err, os.ErrNotExist):
			actual = "missing"
		case err != nil:
			actual = "rejected"
		case m == nil:
			actual = "invalid_result"
		case m.Digest() == digest:
			actual = "matched"
		default:
			actual = "mismatched"
		}
	}
	return actual, reflect.DeepEqual(before, inventory(t, root))
}

func TestFrozenReferences(t *testing.T) {
	profile := os.Getenv("QUALIFIER_PROFILE")
	if profile != "release" && profile != "candidate" {
		t.Fatal("explicit profile required")
	}
	b, err := os.ReadFile("cases.json")
	if err != nil {
		t.Fatal(err)
	}
	var catalog struct {
		Cases []fixtureCase `json:"cases"`
	}
	if err := json.Unmarshal(b, &catalog); err != nil || len(catalog.Cases) != 15 {
		t.Fatal("frozen case catalog required")
	}
	for _, c := range catalog.Cases {
		t.Run(c.ID, func(t *testing.T) {
			actual, unchanged := inspect(t, c.Fixture)
			raw, err := json.Marshal(outcome{c.ID, profile, actual, unchanged})
			if err != nil {
				t.Fatal(err)
			}
			t.Log("QUALIFIER_RESULT " + string(raw))
			if actual != c.Expected[profile] || !unchanged {
				t.Error("unexpected package outcome or scratch-store mutation")
			}
		})
	}
}
