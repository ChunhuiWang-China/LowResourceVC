import os
import argparse
from stgan_adain.solver import Solver
from data_loader import PairDataset, PairTestDataset
from torch.backends import cudnn
import json
from torch.utils import data

def str2bool(v):
    return v.lower() in ('true')

def main(config):
    # For fast training.
    cudnn.benchmark = True

    # Create directories if not exist.
    if not os.path.exists(config.log_dir):
        os.makedirs(config.log_dir)
    if not os.path.exists(config.model_save_dir):
        os.makedirs(config.model_save_dir)
    if not os.path.exists(config.sample_dir):
        os.makedirs(config.sample_dir)
    if not os.path.exists(config.speaker_path):
        raise Exception(f"speaker list {config.speaker_path} does not exist")
    
    with open(config.speaker_path) as f:
        speakers = json.load(f)
    print(f"load speakers {speakers}", flush=True)
    
    # Data loader.
    #train_loader = get_loader(config.train_data_dir, config.batch_size, config.min_length, 'train', speakers, num_workers=config.num_workers,)
    
    train_dataset = PairDataset(config.train_data_dir, speakers, config.min_length)
    train_loader = data.DataLoader(dataset=train_dataset,
                                  batch_size=config.batch_size,
                                  shuffle=(config.mode=='train'),
                                  num_workers=config.num_workers,
                                  drop_last=True)
    
    test_loader = PairTestDataset(config.test_data_dir, config.wav_dir, speakers, src_spk=config.test_src_spk, trg_spk=config.test_trg_spk)

    # Solver for training and testing StarGAN.
    solver = Solver(train_loader, test_loader, config)

    if config.mode == 'train':    
        solver.train()

    # elif config.mode == 'test':
    #     solver.test()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    # Model configuration.
    parser.add_argument('--num_speakers', type=int, default=10, help='dimension of speaker labels')
    parser.add_argument('--lambda_cls', type=float, default=10, help='weight for domain classification loss')
    parser.add_argument('--lambda_rec', type=float, default=10, help='weight for reconstruction loss')
    parser.add_argument('--lambda_gp', type=float, default=10, help='weight for gradient penalty')
    parser.add_argument('--lambda_adv', type=float, default=10, help='weight for adversarial training')
    parser.add_argument('--lambda_id', type=float, default=5, help='weight for id mapping loss')
    parser.add_argument('--lambda_spid', type=float, default=5, help='weight for id mapping loss')
    parser.add_argument('--sampling_rate', type=int, default=16000, help='sampling rate')
    parser.add_argument('--discriminator', type = str, default = 'PatchDiscriminator')
    parser.add_argument('--spenc', type = str, default = 'SPEncoder')
       
    # Training configuration.
    parser.add_argument('--batch_size', type=int, default=8, help='mini-batch size')
    parser.add_argument('--min_length', type=int, default=256 )
    parser.add_argument('--num_iters', type=int, default=500000, help='number of total iterations for training D')
    parser.add_argument('--drop_id_step', type = int, default = 10000, help = 'steps drop id mapping loss')
    parser.add_argument('--num_iters_decay', type=int, default=100000, help='number of iterations for decaying lr')
    parser.add_argument('--g_lr', type=float, default=0.0002, help='learning rate for G')
    parser.add_argument('--d_lr', type=float, default=0.0001, help='learning rate for D')
    parser.add_argument('--n_critic', type=int, default=1, help='number of D updates per each G update')
    parser.add_argument('--beta1', type=float, default=0.5, help='beta1 for Adam optimizer')
    parser.add_argument('--beta2', type=float, default=0.999, help='beta2 for Adam optimizer')
    parser.add_argument('--resume_iters', type=int, default=None, help='resume training from this step')
    parser.add_argument('--device', type=int, default=0, help='choosing cuda device')
    parser.add_argument('--spk_cls', default = False, action = 'store_true', help = 'if or not use spk cls loss for SPEncoder module')

    # Test configuration.
    parser.add_argument('--test_iters', type=int, default=100000, help='test model from this step')
    parser.add_argument('--test_src_spk', type = str, default = 'VCC2SF1')
    parser.add_argument('--test_trg_spk', type = str, default = 'VCC2SM1')

    # Miscellaneous.
    parser.add_argument('--num_workers', type=int, default=1)
    parser.add_argument('--mode', type=str, default='train', choices=['train', 'test'])
    parser.add_argument('--use_tensorboard', type=str2bool, default=True)

    # Directories.
    parser.add_argument('--train_data_dir', type=str, default='./data/mc/train')
    parser.add_argument('--test_data_dir', type=str, default='./data/mc/test')
    parser.add_argument('--wav_dir', type=str, default="./data/VCTK-Corpus/wav16")
    parser.add_argument('--log_dir', type=str, default='./logs')
    parser.add_argument('--model_save_dir', type=str, default='./models')
    parser.add_argument('--sample_dir', type=str, default='./samples')
    parser.add_argument('--speaker_path', type = str)
    # Step size.
    parser.add_argument('--log_step', type=int, default=10)
    parser.add_argument('--sample_step', type=int, default=1000)
    parser.add_argument('--model_save_step', type=int, default=1000)
    parser.add_argument('--lr_update_step', type=int, default=1000)
    
    config = parser.parse_args()
    print(config)
    main(config)
