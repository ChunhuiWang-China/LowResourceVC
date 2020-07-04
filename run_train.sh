#!/bin/bash

source activate torch_0.4
PYTHON=/share/mini1/sw/std/python/anaconda3-2019.07/v3.7/envs/torch_0.4/bin/python

#$PYTHON main.py --wav_dir dump/wav16/

#exp=exp/0624stg2new_4spks/
#exp=exp/0624stg2_4spks/
#exp=exp/0626stg2new_olddis_1/
#exp=exp/0627stg1cin/
#exp=exp/0629stg2_cin1/
#exp=exp/0701stg_adain1/
exp=exp/0704st2new0/
#exp=exp/0703st2ls0/

main_script=main_st2new.py
#main_script=main_st2.py
#main_script=main_st1cin.py
#main_script=main.py
#main_script=main_stgan_adain.py
#main_script=main_st2ls.py

$PYTHON $main_script --wav_dir resmp_wav22050/ \
                    --model_save_dir ${exp}/ckpt/ \
                    --sample_step 10000 \
                    --model_save_step 10000\
                    --log_dir ${exp}/tb/\
                    --num_speakers 4 \
                    --train_data_dir dump/mc/train/ \
                    --test_data_dir dump/mc/eval/ \
                    --sample_dir ./samples/$exp/ \
                    --num_workers 4 \
                    --min_length 256 \
                    --test_src_spk VCC2SF1 \
                    --test_trg_spk VCC2SM1 \
                    --sampling_rate 22050 \
                    --speaker_path ./speaker_used.json \
                    --batch_size 32 \
                    #--resume_iters 80000
                   
