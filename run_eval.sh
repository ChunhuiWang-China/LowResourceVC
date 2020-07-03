#!/bin/bash

source activate torch_0.4
PYTHON=/share/mini1/sw/std/python/anaconda3-2019.07/v3.7/envs/torch_0.4/bin/python

#$PYTHON main.py --wav_dir dump/wav16/

exp=exp/0622stg1_4spks/
$PYTHON evaluate.py  \
                    --convert_dir $exp/converted_samples/ \
                    --mcep_tmp_path $exp/mcep_tmp/ \
                    --sample_rate 22050 \
                    --speaker_path ./speaker_used.json \
                    --pair_list_path ./pair_list.txt
                   
