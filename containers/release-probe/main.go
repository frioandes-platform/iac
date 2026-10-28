// A pipeline demonstration image, not a logistics or telemetry application.
package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
)

var revision = "unversioned"

func main() {
	if len(os.Args) == 2 && os.Args[1] == "--self-test" {
		if len(revision) != 40 {
			os.Exit(1)
		}
		fmt.Println("release-probe self-test passed")
		return
	}
	http.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{"status": "ok", "revision": revision})
	})
	if err := http.ListenAndServe(":8080", nil); err != nil {
		os.Exit(1)
	}
}
