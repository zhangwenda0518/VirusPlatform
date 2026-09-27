SPAdes for Windows (native port) 4.3.0-dev
=========================================

This is a fully self-contained, native-Windows build of the SPAdes genome
assembler. No WSL, Docker, Linux VM, system Python, or compiler is required -
everything (the assembler binaries and a private Python 3.11) is bundled here.

Quick start
-----------
  * Use the "SPAdes Command Prompt" shortcut in the Start Menu, then type:
        spades --help
        spades --test                 (runs the built-in E. coli self-test)
        spades --isolate -1 r1.fq -2 r2.fq -o out_dir

  * If you ticked "Add SPAdes to my PATH" during install, the 'spades' command
    (and metaspades, plasmidspades, rnaspades, coronaspades, ...) works in any
    terminal.

Modes:  --isolate --careful --sc --meta --rna --plasmid --metaviral --rnaviral
        --metaplasmid --bio --corona --sanger --iontorrent --sewage   (all 16 work)

Tips
----
  * On a laptop, cap memory and threads explicitly, e.g.:  spades --isolate -m 8 -t 4 ...
  * Output goes to the -o directory: contigs.fasta, scaffolds.fasta,
    assembly_graph_with_scaffolds.gfa, spades.log.

Project: https://github.com/MrMufasii/spades-windows-final
