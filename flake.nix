{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs";
    flakeUtils.url = "github:numtide/flake-utils";
  };
  outputs = { self, nixpkgs, flakeUtils }:
    flakeUtils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        packages = flakeUtils.lib.flattenTree {
          python310 = pkgs.python310;
          python311 = pkgs.python311;
          python312 = pkgs.python312;
        };
        devShell = pkgs.mkShell {
          buildInputs = with self.packages.${system}; [
            python310
            python311
            python312
          ];
          shellHook = ''
            [[ ! -d .venv ]] && \
              echo "Creating virtualenv ..." && \
              ${pkgs.python310}/bin/python -m \
                venv --copies --upgrade-deps .venv > /dev/null
            source .venv/bin/activate
          '';
        };
      });
}
