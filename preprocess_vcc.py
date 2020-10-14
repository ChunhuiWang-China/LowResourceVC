import librosa
import numpy as np
import os, sys
import argparse
import pyworld
from multiprocessing import cpu_count
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from utils import *
from tqdm import tqdm
from collections import defaultdict
from collections import namedtuple
from sklearn.model_selection import train_test_split
import glob
from os.path import join, basename, exists, isdir
import subprocess
import json
def resample(spk, origin_wavpath, target_wavpath, sr = 16000):
    wavfiles = [i for i in os.listdir(join(origin_wavpath, spk)) if i.endswith(".wav")]
    for wav in wavfiles:
        folder_to = join(target_wavpath, spk)
        os.makedirs(folder_to, exist_ok=True)
        wav_to = join(folder_to, wav)
        wav_from = join(origin_wavpath, spk, wav)
        subprocess.call(['sox', wav_from, "-r", str(sr), wav_to])
    return 0

def resample_to_16k(origin_wavpath, target_wavpath, num_workers=1, sr = 16000):
    os.makedirs(target_wavpath, exist_ok=True)
    spk_folders = os.listdir(origin_wavpath)
    print(f"> Using {num_workers} workers!")
    executor = ProcessPoolExecutor(max_workers=num_workers)
    futures = []
    for spk in spk_folders:
        if isdir(join(origin_wavpath,spk)):
            futures.append(executor.submit(partial(resample, spk, origin_wavpath, target_wavpath, sr)))
    result_list = [future.result() for future in tqdm(futures)]
    print(result_list)

def split_data(paths):
    indices = np.arange(len(paths))
    test_size = 0.1
    train_indices, test_indices = train_test_split(indices, test_size=test_size, random_state=1234)
    train_paths = list(np.array(paths)[train_indices])
    test_paths = list(np.array(paths)[test_indices])
    return train_paths, test_paths

def get_spk_world_feats(spk_fold_path, mc_dir_train, mc_dir_test, sample_rate=16000):
    spk_train_path, spk_eval_path = spk_fold_path
    train_paths = glob.glob(join(spk_train_path, '*.wav'))
    eval_paths = glob.glob(join(spk_eval_path, '*.wav'))
    spk_name = basename(spk_train_path)
    
    
    # train logf0, ap stats
    f0s = []
    coded_sps = []
    for wav_file in train_paths:
        f0, _, _, _, coded_sp = world_encode_wav(wav_file, fs=sample_rate)
        f0s.append(f0)
        coded_sps.append(coded_sp)
    log_f0s_mean, log_f0s_std = logf0_statistics(f0s)
    coded_sps_mean, coded_sps_std = coded_sp_statistics(coded_sps)
    np.savez(join(mc_dir_train, spk_name+'_stats.npz'), 
            log_f0s_mean=log_f0s_mean,
            log_f0s_std=log_f0s_std,
            coded_sps_mean=coded_sps_mean,
            coded_sps_std=coded_sps_std)
    
    for wav_file in tqdm(train_paths):
        wav_nam = basename(wav_file)
        f0, timeaxis, sp, ap, coded_sp = world_encode_wav(wav_file, fs=sample_rate)
        normed_coded_sp = normalize_coded_sp(coded_sp, coded_sps_mean, coded_sps_std)
        mc_path = join(mc_dir_train, spk_name)
        os.makedirs(mc_path, exist_ok = True)
        print(f"f0 {f0.shape} sp {normed_coded_sp.shape} ap {ap.shape}")
        np.save(join(mc_path,wav_nam.replace('.wav', '.npy')), normed_coded_sp, allow_pickle=False)
    
    for wav_file in tqdm(eval_paths):
        wav_nam = basename(wav_file)
        f0, timeaxis, sp, ap, coded_sp = world_encode_wav(wav_file, fs=sample_rate)
        normed_coded_sp = normalize_coded_sp(coded_sp, coded_sps_mean, coded_sps_std)
        mc_path = join(mc_dir_test, spk_name)
        os.makedirs(mc_path, exist_ok = True)
        print(f"f0 {f0.shape} sp {normed_coded_sp.shape} ap {ap.shape}")
        np.save(join(mc_path, wav_nam.replace('.wav', '.npy')), normed_coded_sp, allow_pickle=False)
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()


    sample_rate_default = 16000
    origin_wavpath_default = "./data/VCTK-Corpus/wav48"
    target_wavpath_default = "./data/VCTK-Corpus/wav16"
    mc_dir_train_default = './data/mc/train'
    mc_dir_test_default = './data/mc/test'

    parser.add_argument("--sample_rate", type = int, default = 16000, help = "Sample rate.")
    parser.add_argument("--origin_train_wavpath", type = str, default = origin_wavpath_default, help = "The original wav path to resample.")
    parser.add_argument("--target_train_wavpath", type = str, default = target_wavpath_default, help = "The original wav path to resample.")
    parser.add_argument("--origin_eval_wavpath", type = str, default = origin_wavpath_default, help = "The original wav path to resample.")
    parser.add_argument("--target_eval_wavpath", type = str, default = target_wavpath_default, help = "The original wav path to resample.")
    parser.add_argument("--mc_dir_train", type = str, default = mc_dir_train_default, help = "The directory to store the training features.")
    parser.add_argument("--mc_dir_test", type = str, default = mc_dir_test_default, help = "The directory to store the testing features.")
    parser.add_argument("--num_workers", type = int, default = 30, help = "The number of cpus to use.")
    
    parser.add_argument('--do_resample', action= 'store_true', default = False)
    
    parser.add_argument('--speaker_list', nargs = '+', type = str, default = None)
    argv = parser.parse_args()

    sample_rate = argv.sample_rate
    origin_train_wavpath = argv.origin_train_wavpath
    origin_eval_wavpath = argv.origin_eval_wavpath
    target_train_wavpath = argv.target_train_wavpath
    target_eval_wavpath = argv.target_eval_wavpath
    mc_dir_train = argv.mc_dir_train
    mc_dir_test = argv.mc_dir_test
    num_workers = argv.num_workers if argv.num_workers is not None else cpu_count()

    if argv.do_resample is not None:
        # The original wav in VCTK is 48K, first we want to resample to 16K
        resample_to_16k(origin_train_wavpath, target_train_wavpath, num_workers=num_workers,sr= argv.sample_rate)
        resample_to_16k(origin_eval_wavpath, target_eval_wavpath, num_workers=num_workers,sr= argv.sample_rate)

    # WE only use 10 speakers listed below for this experiment.
    #speaker_used = ['262', '272', '229', '232', '292', '293', '360', '361', '248', '251']
    #speaker_used = ['p'+i for i in speaker_used]

    if not exists(argv.target_train_wavpath):
        raise Exception(f'resample target dir does not exists {argv.target_train_wavpath}')
    
    if not exists(argv.target_eval_wavpath):
        raise Exception(f'resample target dir does not exists {argv.target_eval_wavpath}')
    
    if argv.speaker_list:
        speaker_used = argv.speaker_list
    else:
        speakers = list(glob.glob(join(argv.target_train_wavpath,'*')))
        speaker_used = sorted([basename(sp) for sp in speakers])

    with open('speaker_used.json','w') as f:
        json.dump(speaker_used, f, indent = 4)
    
    print(f"num of speakers {len(speaker_used)} \t speakers {speaker_used}",flush=True)

    ## Next we are to extract the acoustic features (MCEPs, lf0) and compute the corresponding stats (means, stds). 
    # Make dirs to contain the MCEPs
    os.makedirs(mc_dir_train, exist_ok=True)
    os.makedirs(mc_dir_test, exist_ok=True)

    print("number of workers: ", num_workers)
    executor = ProcessPoolExecutor(max_workers=num_workers)

    #work_dir = target_wavpath
    # spk_folders = os.listdir(work_dir)
    # print("processing {} speaker folders".format(len(spk_folders)))
    # print(spk_folders)

    futures = []
    for ind, spk in enumerate(speaker_used):
        print(f"speaker id {ind}")
        spk_train_path = os.path.join(target_train_wavpath, spk)
        spk_test_path = os.path.join(target_eval_wavpath, spk)
        futures.append(executor.submit(partial(get_spk_world_feats, [spk_train_path, spk_test_path], mc_dir_train, mc_dir_test, sample_rate)))
    result_list = [future.result() for future in tqdm(futures)]
    print(result_list)
    sys.exit(0)

